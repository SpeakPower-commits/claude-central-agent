"""Domain vocabulary: the projects, specialists and decision protocol GRIOT works with.

Loaded from agent_manifest.json when present so the manifest is the single
source of truth rather than a decorative file duplicated by constants in code.
"""

from __future__ import annotations

import json
import logging

from .config import APP_DIR

logger = logging.getLogger(__name__)

_FALLBACK_PROJECTS = {
    "speakpower": {"name": "SpeakPower",
                   "description": "Brand storytelling, communications, market development"},
    "tonninyira": {"name": "Tonninyira",
                   "description": "Marketplace product, software, growth and operations"},
    "cuepointe": {"name": "CuePointe",
                  "description": "Community, tournament operations, brand and growth"},
    "ubf": {"name": "UBF",
            "description": "Conservation communications and AI/process automation"},
    "fob": {"name": "FoB",
            "description": "Biodiversity/community ecosystem and operations"},
    "other": {"name": "Portfolio / Other",
              "description": "Business analysis, brand strategy and project operations"},
}

_FALLBACK_AGENTS = [
    "StoryAgent", "MarketAgent", "DataAgent", "DevAgent", "ResearchAgent",
    "GrowthAgent", "OperationsAgent", "BrandAgent", "StrategyAgent",
]

_FALLBACK_STEPS = [
    "UNDERSTAND", "CONTEXT", "EVIDENCE", "DIAGNOSE", "OPTIONS",
    "RECOMMEND", "EXECUTE", "MEASURE", "LEARN",
]


def _load_manifest() -> dict:
    path = APP_DIR / "agent_manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("agent_manifest.json unreadable; using built-in defaults")
        return {}


_manifest = _load_manifest()

_raw_projects: dict = _manifest.get("projects") or _FALLBACK_PROJECTS


def _normalise(entry: str | dict) -> dict:
    """Accept either a bare description string or a {name, description} object.

    The string form is the older manifest shape; keeping it readable means an
    existing manifest does not have to be rewritten to keep working.
    """
    if isinstance(entry, dict):
        return entry
    return {"name": None, "description": str(entry)}


# Slug -> description. This is what the model sees as project context.
PROJECTS: dict[str, str] = {
    slug: _normalise(entry).get("description", "")
    for slug, entry in _raw_projects.items()
}

# Slug -> display name for the interface. Falls back to a title-cased slug,
# which is why acronyms such as UBF and FoB are named explicitly above rather
# than left to be mangled into "Ubf" and "Fob".
PROJECT_NAMES: dict[str, str] = {
    slug: (_normalise(entry).get("name") or slug.replace("-", " ").title())
    for slug, entry in _raw_projects.items()
}

# Specialist key -> display name. Keys are the short forms the router emits.
AGENTS: dict[str, str] = {
    name.removesuffix("Agent").lower(): name
    for name in (_manifest.get("agents") or _FALLBACK_AGENTS)
}

STEPS: list[str] = _manifest.get("decision_protocol") or _FALLBACK_STEPS

MANIFEST_VERSION: str = _manifest.get("version", "unknown")
