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
    "speakpower": "Brand storytelling, communications, market development",
    "tonninyira": "Marketplace product, software, growth and operations",
    "cuepointe": "Community, tournament operations, brand and growth",
    "ubf": "Conservation communications and AI/process automation",
    "fob": "Biodiversity/community ecosystem and operations",
    "other": "Business analysis, brand strategy and project operations",
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

PROJECTS: dict[str, str] = _manifest.get("projects") or _FALLBACK_PROJECTS

# Specialist key -> display name. Keys are the short forms the router emits.
AGENTS: dict[str, str] = {
    name.removesuffix("Agent").lower(): name
    for name in (_manifest.get("agents") or _FALLBACK_AGENTS)
}

STEPS: list[str] = _manifest.get("decision_protocol") or _FALLBACK_STEPS

MANIFEST_VERSION: str = _manifest.get("version", "unknown")
