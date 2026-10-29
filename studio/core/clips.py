"""Reading a hand-written clip list.

This exists so Studio can run with no paid API at all. Choosing which moments
are worth cutting is the only step that needs judgement; everything else is
mechanical. When that judgement comes from a person -- or from a Claude
conversation the operator already pays for -- it arrives here as a few lines of
text instead of an API call.

The format is deliberately forgiving, because it gets pasted into a web form:

    00:03:12  00:03:58  Why most NGOs waste their comms budget
    11:40     12:15     The one question that changes a donor meeting
    # 20:05   20:44     parked - weak ending

Start, end, then an optional title. Times accept SS, MM:SS or HH:MM:SS, and
may be separated by whitespace, a comma, or a dash. Lines beginning with # are
ignored so a clip can be parked without deleting it.
"""

from __future__ import annotations

import re

from . import analyse, config


class ClipFormatError(ValueError):
    """The pasted list could not be read. The message names the line."""


_TIME = r"\d{1,2}(?::\d{1,2}){0,2}(?:\.\d+)?"
_LINE = re.compile(
    rf"^\s*(?P<start>{_TIME})\s*(?:,|--|-|–|to|\s)\s*(?P<end>{_TIME})\s*(?P<title>.*)$",
    re.IGNORECASE,
)


def parse_timecode(value: str) -> float:
    """SS, MM:SS or HH:MM:SS to seconds."""
    parts = value.strip().split(":")
    if not parts or len(parts) > 3:
        raise ClipFormatError(f"Not a timecode: {value!r}")
    seconds = 0.0
    for part in parts:
        if not re.fullmatch(r"\d+(\.\d+)?", part):
            raise ClipFormatError(f"Not a timecode: {value!r}")
        seconds = seconds * 60 + float(part)
    return seconds


def parse(text: str, duration: float) -> list[dict[str, object]]:
    """Turn pasted text into the same clip shape the model path produces.

    Validated against the real duration by the same code that checks the
    model's output, so a typed timecode cannot produce a corrupt render any
    more than a hallucinated one can.
    """
    raw: list[dict[str, object]] = []
    problems: list[str] = []

    # A GitHub workflow_dispatch input is a single-line box, so a list typed
    # there cannot contain newlines. Semicolons separate clips just as well,
    # and a title is very unlikely to need one.
    normalised = text.replace(";", "\n")

    for number, line in enumerate(normalised.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = _LINE.match(stripped)
        if not match:
            problems.append(f"line {number}: could not read {stripped[:60]!r}")
            continue

        try:
            start = parse_timecode(match.group("start"))
            end = parse_timecode(match.group("end"))
        except ClipFormatError as error:
            problems.append(f"line {number}: {error}")
            continue

        if end <= start:
            problems.append(f"line {number}: end is not after start")
            continue

        title = match.group("title").strip(" \t-–—|,")
        raw.append({
            "start_seconds": start,
            "end_seconds": end,
            "title": title or f"clip-{number}",
            "hook": "",
            "why": "chosen by hand",
        })

    if not raw:
        detail = "\n  ".join(problems) if problems else "the list was empty"
        raise ClipFormatError(
            "No clips could be read from the list you pasted.\n  " + detail +
            "\n\nExpected one clip per line, for example:\n"
            "  00:03:12  00:03:58  Why most NGOs waste their comms budget"
        )

    # Same validation the model's output gets: range, length, and overlap.
    validated = analyse._validate_clips(raw, duration)
    if not validated:
        floor = analyse.minimum_clip_seconds(duration)
        raise ClipFormatError(
            f"{len(raw)} clips were read but none survived checking against a "
            f"recording {int(duration)}s long. Each clip must sit inside the "
            f"recording and last at least {floor:.0f}s."
        )

    if problems:
        # Report what was skipped rather than silently dropping lines.
        print("  Some lines were skipped:", flush=True)
        for problem in problems:
            print(f"    {problem}", flush=True)

    return validated


def as_analysis(clips: list[dict[str, object]], title: str = "") -> dict[str, object]:
    """Wrap a hand-written list in the shape the rest of the pipeline expects."""
    return {
        "episode_title": title.strip() or "Untitled recording",
        "summary": "",
        "editorial_note": "Clips chosen by hand; no model was used.",
        "clips": clips,
        "show_notes": "",
        "social_captions": [],
        "blog_outline": "",
        "model": "none (clips supplied)",
    }
