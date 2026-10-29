"""Configuration for SpeakPower Studio.

Studio runs on a small server you rent, not on your computer, because the
office desktop cannot have software installed on it. Everything you do happens
in a browser.

All settings are read from the environment once, at import.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load a .env sitting beside the app when one exists. Optional, so the app also
# works when the host sets real environment variables, as Railway and Render do.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # python-dotenv is a convenience, not a requirement
    pass


STUDIO_DIR = Path(__file__).resolve().parent.parent
# On a hosted box this should point at the mounted disk, otherwise finished
# videos vanish on every redeploy.
WORKSPACE_DIR = Path(os.getenv("STUDIO_WORKSPACE", STUDIO_DIR / "workspace"))
JOBS_DIR = WORKSPACE_DIR / "jobs"
STATIC_DIR = STUDIO_DIR / "static"

# --- Secrets ----------------------------------------------------------------

# Studio sits on the public internet, so it is password-gated. Without this set
# the app refuses to start rather than exposing your footage to anyone who
# finds the URL.
STUDIO_PASSWORD = os.getenv("STUDIO_PASSWORD", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Optional. When set, transcription goes to Deepgram instead of running the
# speech model on the server's CPU: minutes rather than tens of minutes, for
# roughly a cent per minute of audio. Without it Studio falls back to local
# transcription, which is free but slow on a small box.
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# --- Models -----------------------------------------------------------------

# Sonnet is the default because clip selection reads a whole transcript and the
# cost difference matters at volume. Set STUDIO_MODEL=claude-opus-5 when a
# piece is worth the extra judgement.
ANALYSIS_MODEL = os.getenv("STUDIO_MODEL", "claude-sonnet-5-5")

# Local speech model, used only when DEEPGRAM_API_KEY is absent.
# tiny/base/small/medium/large-v3 -- "small" is the sensible default on a CPU
# box; "medium" is markedly better on accented English and about 3x slower.
WHISPER_MODEL = os.getenv("STUDIO_WHISPER_MODEL", "small")
WHISPER_COMPUTE = os.getenv("STUDIO_WHISPER_COMPUTE", "int8")

# --- Output format ----------------------------------------------------------

SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
SHORT_FPS = 30

# EBU R128 loudness targets. -16 LUFS is the podcast convention that Spotify,
# Apple and YouTube all normalise toward; -1.5 dBTP leaves headroom so lossy
# encoding downstream cannot clip.
TARGET_LUFS = -16.0
TARGET_TRUE_PEAK = -1.5
TARGET_LOUDNESS_RANGE = 11.0

# Burned-in caption styling, in libass terms.
#
# These numbers look far too small for a 1080-wide frame. They are correct:
# libass lays an SRT out in its own 384x288 space and scales the result up, so
# FontSize=14 renders large. Forcing frame-pixel units with the subtitles
# filter's original_size option looks like the right fix and is not -- it
# pushes the text clean off the frame and nothing renders at all. If you adjust
# these, scale them (roughly frame_pixels / 6.7) rather than substituting pixel
# values.
CAPTION_STYLE = (
    "FontName=DejaVu Sans,FontSize=14,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
    "BorderStyle=1,Outline=1,Shadow=0,"
    "Alignment=2,MarginV=70,MarginL=18,MarginR=18"
)

# --- Editing defaults -------------------------------------------------------

SILENCE_NOISE_FLOOR_DB = -32.0
SILENCE_MIN_SECONDS = 0.9
SILENCE_PAD_SECONDS = 0.12

TARGET_CLIP_COUNT = int(os.getenv("STUDIO_CLIP_COUNT", "8"))
CLIP_MIN_SECONDS = 20
CLIP_MAX_SECONDS = 75

# A cap so one enormous file cannot fill the server's disk.
MAX_SOURCE_GB = float(os.getenv("STUDIO_MAX_SOURCE_GB", "6"))


class ConfigError(RuntimeError):
    """Raised at startup when Studio is configured in a way that is unsafe."""


def validate() -> None:
    """Checks that apply however Studio is run.

    Deliberately does not demand a password: when Studio runs as a GitHub
    Action there is no server to protect, and the repository's own access
    control is the boundary.
    """
    if not ANTHROPIC_API_KEY:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set, so the moments cannot be chosen. "
            "Add it under Settings -> Secrets and variables -> Actions."
        )
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def validate_for_server() -> None:
    """Extra checks that only matter when Studio is exposed on the internet."""
    validate()
    if not STUDIO_PASSWORD:
        raise ConfigError(
            "STUDIO_PASSWORD is not set. A hosted Studio would be open to "
            "anyone who found the URL."
        )
    if len(STUDIO_PASSWORD) < 12:
        raise ConfigError(
            "STUDIO_PASSWORD is too short to resist guessing. Use at least 12 "
            "characters."
        )


def transcription_backend() -> str:
    """Which speech engine will be used, for display in the interface."""
    return "deepgram" if DEEPGRAM_API_KEY else "local"


def model_ready() -> bool:
    """Whether Claude analysis can run. Without a key Studio still transcribes
    and cleans the audio; it just cannot choose the moments."""
    return bool(ANTHROPIC_API_KEY)
