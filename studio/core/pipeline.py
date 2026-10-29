"""The pipeline: one video in, a folder of finished assets out.

Runs on a background thread so the browser can poll for progress. Every stage
reports what it is doing in plain language, because a progress bar that only
says "processing" for forty minutes is indistinguishable from a hang.

The order matters. Transcription comes first because everything else depends on
the words; the long edit is rendered before the shorts because it is the asset
most likely to be wanted even if a later stage fails.
"""

from __future__ import annotations

import json
import re
import traceback
from pathlib import Path
from typing import Any

from . import analyse, config, fetch, jobs, media, transcribe


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:60] or "clip"


def _write_text_assets(result: dict[str, Any], outputs_dir: Path) -> list[str]:
    """Save the written deliverables as files the browser can offer."""
    written: list[str] = []

    show_notes = outputs_dir / "show-notes.md"
    lines = [f"# {result['episode_title']}", ""]
    if result.get("summary"):
        lines += [result["summary"], ""]
    if result.get("show_notes"):
        lines += [result["show_notes"], ""]
    show_notes.write_text("\n".join(lines), encoding="utf-8")
    written.append(show_notes.name)

    if result.get("blog_outline"):
        blog = outputs_dir / "blog-outline.md"
        blog.write_text(result["blog_outline"], encoding="utf-8")
        written.append(blog.name)

    if result.get("social_captions"):
        captions = outputs_dir / "social-captions.md"
        body = ["# Captions", ""]
        for index, caption in enumerate(result["social_captions"], start=1):
            body += [f"## {index}", caption, ""]
        captions.write_text("\n".join(body), encoding="utf-8")
        written.append(captions.name)

    return written


def run(job_id: str, source: str, source_kind: str,
        context: str = "", style: str = "blur",
        skip_episode: bool = False) -> None:
    """Execute the whole pipeline for one job, recording progress as it goes."""
    directory = jobs.job_dir(job_id)
    outputs_dir = directory / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    def note(message: str) -> None:
        """Record progress, and echo it so the Actions log reads like a status
        report rather than forty silent minutes."""
        jobs.update(job_id, message=message)
        print(f"    {message}", flush=True)

    def stage(name: str) -> None:
        jobs.set_stage(job_id, name)
        print(f"\n==> {name}", flush=True)

    try:
        # --- 1. Get the video -------------------------------------------------
        stage("Fetching the video")
        if source_kind == "link":
            video_path = fetch.fetch_from_url(source, directory, note)
        else:
            video_path = Path(source)
            if not video_path.is_file():
                raise fetch.FetchError("The uploaded file could not be found.")
        fetch.check_size(video_path)

        duration = media.probe_duration(video_path)
        if not media.has_audio_stream(video_path):
            raise media.MediaError(
                "That file has no audio track, so there is nothing to work from."
            )
        jobs.update(job_id, duration_minutes=round(duration / 60, 1))

        # --- 2. Transcribe ----------------------------------------------------
        stage("Listening to the audio")
        audio_path = directory / "audio.wav"
        media.extract_audio(video_path, audio_path)
        segments = transcribe.transcribe(audio_path, note)

        srt_path = outputs_dir / "captions.srt"
        transcribe.write_srt(segments, srt_path)
        transcript_path = outputs_dir / "transcript.txt"
        transcribe.write_transcript(segments, transcript_path)
        transcribe.write_segments(segments, directory / "segments.json")
        # The stripped WAV is a disposable intermediate worth 100MB of disk.
        audio_path.unlink(missing_ok=True)

        # --- 3. Choose the moments -------------------------------------------
        stage("Choosing the moments")
        analysis = analyse.analyse(
            transcript_path.read_text(encoding="utf-8"), duration, context
        )
        (directory / "analysis.json").write_text(
            json.dumps(analysis, indent=1), encoding="utf-8"
        )
        jobs.update(
            job_id,
            episode_title=analysis["episode_title"],
            editorial_note=analysis.get("editorial_note", ""),
        )

        # --- 4. Clean the full episode ---------------------------------------
        stage("Cleaning the full episode")
        episode_path: Path | None = outputs_dir / "episode-cleaned.mp4"
        if skip_episode:
            # The long edit is by far the slowest stage and the largest file.
            # On a free runner with a storage quota it is often not worth it.
            note("Skipped (--skip-episode)")
            tighten_stats = {"skipped": True}
            episode_path = None
        else:
            try:
                tighten_stats = media.tighten(video_path, episode_path, note)
            except media.MediaError as error:
                # A failed long edit must not cost the shorts, worth more.
                note(f"Could not clean the episode: {error}")
                tighten_stats = {"error": str(error)}
                episode_path = None

        # --- 5. Cut the shorts ------------------------------------------------
        stage("Cutting the shorts")
        shorts: list[dict[str, Any]] = []
        for index, clip in enumerate(analysis["clips"], start=1):
            note(f"Cutting short {index} of {len(analysis['clips'])}")
            name = f"{index:02d}-{_slugify(clip['title'])}"
            clip_path = outputs_dir / f"{name}.mp4"

            cue_path = directory / f"cues_{index:03d}.srt"
            subtitle_path = (
                cue_path
                if transcribe.slice_srt(srt_path, clip["start"], clip["end"], cue_path)
                else None
            )
            try:
                media.cut_short(
                    video_path, clip["start"], clip["end"],
                    clip_path, subtitle_path, style,
                )
            except media.MediaError:
                continue
            finally:
                cue_path.unlink(missing_ok=True)

            poster = outputs_dir / f"{name}.jpg"
            media.thumbnail(clip_path, poster, at_seconds=1.0)

            shorts.append({
                "file": clip_path.name,
                "poster": poster.name if poster.exists() else None,
                "title": clip["title"],
                "hook": clip.get("hook", ""),
                "why": clip.get("why", ""),
                "seconds": round(clip["end"] - clip["start"], 1),
                "source_start": transcribe.format_timestamp(clip["start"]),
            })

        # --- 6. Write the text ------------------------------------------------
        stage("Writing the text")
        text_files = _write_text_assets(analysis, outputs_dir)
        text_files += [transcript_path.name, srt_path.name]

        jobs.finish(job_id, {
            "shorts": shorts,
            "episode": episode_path.name if episode_path else None,
            "episode_stats": tighten_stats,
            "text": text_files,
        })

    except (fetch.FetchError, media.MediaError,
            transcribe.TranscriptionError, analyse.AnalysisError) as error:
        # Expected failures: the message is already written for a person.
        jobs.fail(job_id, str(error))
    except Exception as error:  # noqa: BLE001 - last resort, must not lose the job
        jobs.fail(job_id, f"Unexpected error: {error}")
        (jobs.job_dir(job_id) / "traceback.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
