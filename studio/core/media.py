"""ffmpeg operations: probing, dead-air removal, loudness, vertical shorts.

Every function here shells out to ffmpeg rather than using a Python wrapper.
Wrappers hide the command that actually ran, which is the first thing you want
when a render fails on a real client file.

Two decisions worth knowing about:

* Everything re-encodes rather than stream-copying. Stream copying is far
  faster but cuts only on keyframes, which puts each edit up to several seconds
  away from where it belongs. Interview edits have to be frame-accurate.
* Cut segments are written to files and joined with the concat demuxer rather
  than built into one filtergraph. A filtergraph with thousands of nodes
  exhausts memory on a small server; an hour of speech can easily produce
  hundreds of segments.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config


class MediaError(RuntimeError):
    """A render or probe failed. The message is meant to be shown to a person."""


def ensure_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise MediaError(
                f"{tool} is not installed on the server. The Docker image "
                "installs it; if you deployed without Docker, add ffmpeg."
            )


def _run(command: list[str], what: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        # ffmpeg's useful error is always in the last few lines of stderr.
        tail = "\n".join(result.stderr.strip().splitlines()[-6:])
        raise MediaError(f"{what} failed:\n{tail}")
    return result


def probe_duration(media_path: Path) -> float:
    """Length in seconds."""
    ensure_ffmpeg()
    result = _run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        f"Reading {media_path.name}",
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise MediaError(
            f"{media_path.name} does not look like a video or audio file."
        ) from None


def has_audio_stream(media_path: Path) -> bool:
    """A video with no audio cannot be transcribed, and that is worth catching
    before spending minutes on it."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0", str(media_path),
        ],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    """A 16kHz mono WAV, which is what speech models expect.

    Transcribing the original file works but re-decodes gigabytes repeatedly;
    an hour as a stripped WAV is around 100MB.
    """
    _run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(audio_path),
        ],
        "Extracting audio",
    )
    return audio_path


def detect_silences(media_path: Path) -> list[tuple[float, float]]:
    """Spans of silence, from ffmpeg's silencedetect filter.

    silencedetect reports on stderr while decoding, so the output is parsed
    rather than read from an exit status.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(media_path),
            "-af", (
                f"silencedetect=noise={config.SILENCE_NOISE_FLOOR_DB}dB"
                f":d={config.SILENCE_MIN_SECONDS}"
            ),
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )

    silences: list[tuple[float, float]] = []
    pending_start: float | None = None
    for line in result.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if start_match:
            pending_start = max(0.0, float(start_match.group(1)))
            continue
        end_match = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if end_match and pending_start is not None:
            silences.append((pending_start, float(end_match.group(1))))
            pending_start = None
    return silences


def keep_segments(silences: list[tuple[float, float]],
                  duration: float) -> list[tuple[float, float]]:
    """Invert silences into the spans worth keeping.

    A little padding is left either side of speech: cutting flush to the
    waveform clips consonants and sounds unnatural. A breath of room is what
    makes an edit inaudible.
    """
    pad = config.SILENCE_PAD_SECONDS
    segments: list[tuple[float, float]] = []
    cursor = 0.0
    for silence_start, silence_end in silences:
        end = min(duration, silence_start + pad)
        if end - cursor > 0.05:
            segments.append((cursor, end))
        cursor = max(0.0, silence_end - pad)
    if duration - cursor > 0.05:
        segments.append((cursor, duration))
    return segments


def tighten(video_path: Path, output_path: Path,
            progress=None) -> dict[str, float]:
    """Remove dead air and normalise loudness. Returns what it did, for display.

    Loudness is not a matter of taste: -16 LUFS is the podcast standard that
    Spotify, Apple and YouTube normalise toward, and it is the single thing
    that most separates an amateur podcast from a professional one.
    """
    ensure_ffmpeg()
    duration = probe_duration(video_path)
    silences = detect_silences(video_path)
    segments = keep_segments(silences, duration)
    if not segments:
        raise MediaError(
            "The whole recording registered as silence. The audio track may be "
            "empty or extremely quiet."
        )

    kept = sum(end - start for start, end in segments)

    with tempfile.TemporaryDirectory(prefix="tighten_") as temporary:
        temporary_path = Path(temporary)
        segment_files: list[Path] = []

        for index, (start, end) in enumerate(segments):
            segment_file = temporary_path / f"seg_{index:05d}.mp4"
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", str(video_path),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-avoid_negative_ts", "make_zero",
                    str(segment_file),
                ],
                capture_output=True, text=True,
            )
            # One unusable segment should not lose the whole episode.
            if result.returncode == 0 and segment_file.exists():
                segment_files.append(segment_file)
            if progress and index % 20 == 0:
                progress(f"Cutting dead air ({index + 1} of {len(segments)})")

        if not segment_files:
            raise MediaError("No usable segments were produced.")

        list_file = temporary_path / "segments.txt"
        list_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in segment_files),
            encoding="utf-8",
        )

        if progress:
            progress("Balancing the sound")
        _run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-af", (
                    f"loudnorm=I={config.TARGET_LUFS}"
                    f":TP={config.TARGET_TRUE_PEAK}"
                    f":LRA={config.TARGET_LOUDNESS_RANGE}"
                ),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path),
            ],
            "Joining the episode",
        )

    return {
        "original_minutes": round(duration / 60, 1),
        "final_minutes": round(kept / 60, 1),
        "removed_minutes": round((duration - kept) / 60, 1),
        "silences": len(silences),
    }


def _subtitle_filter(subtitle_path: Path) -> str:
    """The subtitles filter, with the path escaped for the filtergraph parser."""
    escaped = (
        subtitle_path.as_posix()
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )
    return f"subtitles='{escaped}':force_style='{config.CAPTION_STYLE}'"


def vertical_filter(style: str, subtitle_path: Path | None) -> str:
    """Reframe to 1080x1920, optionally burning captions in.

    Two framings, because neither suits every interview:

    * "blur" keeps the whole frame, letterboxed over a blurred copy of itself.
      Safe when two people share the shot.
    * "crop" fills the frame and centre-crops. Punchier, but it will cut off a
      speaker who is not centred.
    """
    width, height = config.SHORT_WIDTH, config.SHORT_HEIGHT
    if style == "crop":
        reframe = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    else:
        reframe = (
            f"split[original][background];"
            f"[background]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},gblur=sigma=28[blurred];"
            f"[original]scale={width}:-2[fitted];"
            f"[blurred][fitted]overlay=(W-w)/2:(H-h)/2"
        )
    if subtitle_path is None:
        return reframe
    return f"{reframe},{_subtitle_filter(subtitle_path)}"


def cut_short(video_path: Path, start: float, end: float, output_path: Path,
              subtitle_path: Path | None, style: str = "blur") -> None:
    """Render one vertical, captioned clip."""
    ensure_ffmpeg()
    _run(
        [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(video_path),
            "-vf", vertical_filter(style, subtitle_path),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "160k",
            "-r", str(config.SHORT_FPS),
            # So the clip starts playing before it has fully downloaded.
            "-movflags", "+faststart",
            str(output_path),
        ],
        f"Cutting {output_path.name}",
    )


def thumbnail(video_path: Path, output_path: Path, at_seconds: float = 1.0) -> None:
    """A still from a clip, used as the preview tile in the interface."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{at_seconds:.2f}", "-i", str(video_path),
            "-frames:v", "1", "-vf", "scale=270:-2", str(output_path),
        ],
        capture_output=True, text=True,
    )
