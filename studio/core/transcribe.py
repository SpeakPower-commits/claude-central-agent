"""Turning speech into timed text.

Two backends, chosen by whether DEEPGRAM_API_KEY is set:

* Deepgram -- an hour of audio in a minute or two, for roughly a cent a
  minute. Worth it on a small server, where the local model is slow.
* faster-whisper -- runs on the server's own CPU. Free, private, and slow:
  tens of minutes for an hour of audio on a cheap box.

Both return the same shape, so nothing downstream knows or cares which ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from . import config


class TranscriptionError(RuntimeError):
    """Speech recognition failed, in terms worth showing to a person."""


ProgressCallback = Callable[[str], None]


def format_timestamp(seconds: float, *, srt: bool = False) -> str:
    """Seconds to a readable timestamp. SRT demands HH:MM:SS,mmm exactly."""
    seconds = max(0.0, seconds)
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if srt:
        milliseconds = int(round((seconds - int(seconds)) * 1000))
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def _transcribe_deepgram(audio_path: Path,
                         progress: ProgressCallback | None) -> list[dict[str, Any]]:
    """Send the stripped WAV to Deepgram and reshape its response."""
    import httpx

    if progress:
        progress("Sending audio for transcription")

    # nova-3 handles accented English markedly better than older models, which
    # is the whole reason this backend exists.
    url = (
        "https://api.deepgram.com/v1/listen"
        "?model=nova-3&smart_format=true&punctuate=true&utterances=true"
    )
    try:
        with httpx.Client(timeout=900.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/wav",
                },
                content=audio_path.read_bytes(),
            )
    except httpx.HTTPError as error:
        raise TranscriptionError(f"Could not reach Deepgram: {error}") from error

    if response.status_code == 401:
        raise TranscriptionError("Deepgram rejected the API key.")
    if response.status_code != 200:
        raise TranscriptionError(
            f"Deepgram returned {response.status_code}: {response.text[:300]}"
        )

    payload = response.json()
    utterances = payload.get("results", {}).get("utterances") or []
    if not utterances:
        raise TranscriptionError(
            "No speech was found in the audio. Check the recording has a voice "
            "track."
        )

    return [
        {
            "start": float(utterance["start"]),
            "end": float(utterance["end"]),
            "text": utterance["transcript"].strip(),
            "speaker": utterance.get("speaker"),
        }
        for utterance in utterances
        if utterance.get("transcript", "").strip()
    ]


def _transcribe_local(audio_path: Path,
                      progress: ProgressCallback | None) -> list[dict[str, Any]]:
    """Run faster-whisper on the server's CPU."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise TranscriptionError(
            "faster-whisper is not installed and no DEEPGRAM_API_KEY is set, "
            "so there is no way to transcribe."
        ) from error

    if progress:
        progress(f"Loading the speech model ({config.WHISPER_MODEL})")
    model = WhisperModel(
        config.WHISPER_MODEL,
        device="cpu",
        compute_type=config.WHISPER_COMPUTE,
    )

    if progress:
        progress("Listening (this is the slow part)")
    # vad_filter skips silence rather than inventing words over it, which is a
    # real failure mode on recordings with long gaps.
    iterator, _info = model.transcribe(
        str(audio_path), word_timestamps=False, vad_filter=True
    )

    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(iterator):
        text = segment.text.strip()
        if not text:
            continue
        segments.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": text,
            "speaker": None,
        })
        if progress and index % 25 == 0 and index:
            progress(f"Listening -- {format_timestamp(segment.end)} so far")

    if not segments:
        raise TranscriptionError("No speech was found in the audio.")
    return segments


def transcribe(audio_path: Path,
               progress: ProgressCallback | None = None) -> list[dict[str, Any]]:
    """Transcribe, using whichever backend is configured."""
    if config.DEEPGRAM_API_KEY:
        return _transcribe_deepgram(audio_path, progress)
    return _transcribe_local(audio_path, progress)


def write_srt(segments: list[dict[str, Any]], path: Path) -> Path:
    """Subtitles, for burning into shorts and for uploading to YouTube."""
    lines = []
    for index, segment in enumerate(segments, start=1):
        start = format_timestamp(segment["start"], srt=True)
        end = format_timestamp(segment["end"], srt=True)
        lines.append(f"{index}\n{start} --> {end}\n{segment['text']}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_transcript(segments: list[dict[str, Any]], path: Path) -> Path:
    """A readable transcript with [mm:ss] markers."""
    lines = []
    for segment in segments:
        marker = format_timestamp(segment["start"])
        speaker = segment.get("speaker")
        prefix = f"[{marker}] " + (f"Speaker {speaker}: " if speaker is not None else "")
        lines.append(prefix + segment["text"])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_segments(segments: list[dict[str, Any]], path: Path) -> Path:
    path.write_text(json.dumps(segments, indent=1), encoding="utf-8")
    return path


def slice_srt(srt_path: Path, start: float, end: float, output_path: Path) -> bool:
    """Write an SRT covering [start, end], rebased so the clip begins at zero.

    The subtitles filter reads a file's own timings, so a trimmed clip needs its
    cues shifted or every caption lands at the wrong moment.
    """
    import re

    pattern = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*\n"
        r"(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    content = srt_path.read_text(encoding="utf-8", errors="replace")

    cues: list[str] = []
    index = 1
    for match in pattern.finditer(content):
        cue_start = (int(match.group(2)) * 3600 + int(match.group(3)) * 60
                     + int(match.group(4)) + int(match.group(5)) / 1000)
        cue_end = (int(match.group(6)) * 3600 + int(match.group(7)) * 60
                   + int(match.group(8)) + int(match.group(9)) / 1000)
        if cue_end <= start or cue_start >= end:
            continue
        text = match.group(10).strip()
        if not text:
            continue
        cues.append(
            f"{index}\n"
            f"{format_timestamp(max(0.0, cue_start - start), srt=True)} --> "
            f"{format_timestamp(min(end, cue_end) - start, srt=True)}\n"
            f"{text}\n"
        )
        index += 1

    if not cues:
        return False
    output_path.write_text("\n".join(cues), encoding="utf-8")
    return True
