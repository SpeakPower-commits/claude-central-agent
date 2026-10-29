"""The editorial judgement: which moments are worth cutting, and what to call them.

This is the part that is actually AI. Everything else in Studio is mechanical
-- ffmpeg can cut anything you point it at, but deciding *what* to cut out of
an hour of talking is the work a client is paying for.

The model is given the transcript with timestamps and asked for strict JSON.
Its times are then validated against the real duration, because a model that
is confidently wrong about a timecode would otherwise produce a clip that
starts mid-word or runs past the end of the file.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import config


class AnalysisError(RuntimeError):
    """Clip selection failed, in terms worth showing to a person."""


SYSTEM_PROMPT = """\
You are the senior editor at SpeakPower, a communications firm. You are given \
the transcript of an interview, podcast or talk, with [mm:ss] timestamps.

Your job is to find the moments worth publishing as short vertical videos, and \
to write the text assets that go around the episode.

What makes a good short:
- It is SELF-CONTAINED. A viewer with no context understands it alone.
- It opens on something that earns attention in the first three seconds: a \
claim, a number, a contradiction, a confession, a sharp question.
- It completes a thought. It does not stop mid-sentence or mid-argument.
- It carries ONE idea, not three.

What makes a bad short, and you must reject these:
- Pleasantries, introductions, thanks, housekeeping, sign-offs.
- A point that only lands if you heard the previous ten minutes.
- Someone agreeing, or restating what the other person just said.
- Vague inspiration with no specific claim in it.

Be ruthless. Returning four genuinely strong clips is far better than padding \
to the requested number with weak ones. If the material is thin, say so in \
`editorial_note` and return fewer.

Timestamps must come from the transcript markers. Start a clip slightly BEFORE \
the speaker begins the thought, and end it just AFTER the thought lands.
"""

RESPONSE_SHAPE = """\
Reply with JSON only. No prose outside the JSON, no markdown fences.

{
  "episode_title": "a specific, non-generic title for the full episode",
  "summary": "2-3 sentences on what this episode actually covers",
  "editorial_note": "your honest read on the material, including anything weak",
  "clips": [
    {
      "start_seconds": 192,
      "end_seconds": 238,
      "title": "short filename-friendly label, 3-7 words",
      "hook": "the first line of the caption, written to stop a scroll",
      "why": "one sentence on why this clip works"
    }
  ],
  "show_notes": "markdown: a paragraph, then bulleted key points with [mm:ss]",
  "social_captions": [
    "a ready-to-post caption for one of the clips, including hashtags"
  ],
  "blog_outline": "markdown: a working title and 4-6 section headings"
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    """Parse the model's reply, tolerating fences it was asked not to use."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: the outermost {...} in the reply.
        brace = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not brace:
            raise AnalysisError(
                "The model did not return usable JSON. Try running the job again."
            ) from None
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError as error:
            raise AnalysisError(f"Could not read the model's reply: {error}") from error


def minimum_clip_seconds(duration: float) -> float:
    """The shortest acceptable clip, scaled to the source.

    A flat 20-second floor is right for an hour-long podcast and wrong for a
    three-minute talking head: every clip would be rejected and the job would
    fail with "no usable clips", which tells the operator nothing. The floor
    therefore follows the source length, never dropping below 8 seconds.
    """
    return min(config.CLIP_MIN_SECONDS, max(8.0, duration * 0.15))


def _validate_clips(raw_clips: Any, duration: float) -> list[dict[str, Any]]:
    """Keep only clips with times that make sense against the real file.

    A model can be confidently wrong about a timecode. Rather than trusting it,
    anything out of range, inverted, or absurdly long is dropped here -- a
    missing clip is a far smaller problem than a corrupt render.
    """
    if not isinstance(raw_clips, list):
        return []

    floor = minimum_clip_seconds(duration)
    clips: list[dict[str, Any]] = []
    for entry in raw_clips:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("start_seconds"))
            end = float(entry.get("end_seconds"))
        except (TypeError, ValueError):
            continue

        start = max(0.0, min(start, duration))
        end = max(0.0, min(end, duration))
        if end - start < floor:
            continue
        if end - start > config.CLIP_MAX_SECONDS:
            # Trim rather than discard: the opening of a long pick is usually
            # the strong part.
            end = start + config.CLIP_MAX_SECONDS

        title = str(entry.get("title") or "untitled").strip()
        clips.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "title": title[:80],
            "hook": str(entry.get("hook") or "").strip()[:300],
            "why": str(entry.get("why") or "").strip()[:300],
        })

    # Overlapping clips produce near-duplicate shorts, which looks careless.
    clips.sort(key=lambda clip: clip["start"])
    deduplicated: list[dict[str, Any]] = []
    for clip in clips:
        if deduplicated and clip["start"] < deduplicated[-1]["end"] - 2:
            continue
        deduplicated.append(clip)
    return deduplicated


def analyse(transcript_text: str, duration: float,
            context: str = "") -> dict[str, Any]:
    """Ask Claude for the clip list and the text assets."""
    if not config.model_ready():
        raise AnalysisError(
            "ANTHROPIC_API_KEY is not set, so the moments cannot be chosen. "
            "Set it in your host's environment variables."
        )

    try:
        import anthropic
    except ImportError as error:
        raise AnalysisError("The anthropic package is not installed.") from error

    about = f"\nWhat this recording is:\n{context.strip()}\n" if context.strip() else ""
    user_message = (
        f"Recording length: {int(duration // 60)} minutes {int(duration % 60)} seconds."
        f"{about}\n"
        f"Find up to {config.TARGET_CLIP_COUNT} clips, each between "
        f"{config.CLIP_MIN_SECONDS} and {config.CLIP_MAX_SECONDS} seconds.\n\n"
        f"{RESPONSE_SHAPE}\n"
        f"TRANSCRIPT\n----------\n{transcript_text}"
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=config.ANALYSIS_MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as error:  # the SDK raises a family of connection errors
        raise AnalysisError(f"Claude could not be reached: {error}") from error

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    if not text.strip():
        raise AnalysisError("Claude returned an empty reply.")

    payload = _extract_json(text)
    proposed = payload.get("clips") if isinstance(payload.get("clips"), list) else []
    clips = _validate_clips(proposed, duration)
    if not clips:
        # Say which of the two failures this was, so the operator knows whether
        # to re-run or to accept that the material has nothing in it.
        if proposed:
            raise AnalysisError(
                f"The editor proposed {len(proposed)} clips but none survived "
                f"checking against the {int(duration)}s recording -- the "
                "timecodes were out of range or shorter than "
                f"{minimum_clip_seconds(duration):.0f}s. Running the job again "
                "usually fixes this."
            )
        raise AnalysisError(
            "No clips were found. The recording may be too short, or mostly "
            "conversation without a self-contained point in it."
        )

    captions = payload.get("social_captions")
    return {
        "episode_title": str(payload.get("episode_title") or "Untitled episode")[:200],
        "summary": str(payload.get("summary") or "").strip(),
        "editorial_note": str(payload.get("editorial_note") or "").strip(),
        "clips": clips,
        "show_notes": str(payload.get("show_notes") or "").strip(),
        "social_captions": [str(item) for item in captions] if isinstance(captions, list) else [],
        "blog_outline": str(payload.get("blog_outline") or "").strip(),
        "model": config.ANALYSIS_MODEL,
    }
