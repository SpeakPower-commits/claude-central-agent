"""Runtime configuration, resolved once at import.

Every environment-dependent value lives here so the rest of the application
never reads os.environ directly. That keeps configuration auditable and makes
the serverless/local split explicit rather than scattered through call sites.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths -------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"

# --- Claude ------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Primary reasoning model. Strategic analysis is the product, so this stays on
# the most capable tier unless deliberately overridden.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5").strip()

# Cheap worker model used only to distil an exchange into a memory row. This is
# bulk extraction, not reasoning, so it does not warrant the primary model.
MEMORY_MODEL = os.getenv("GRIOT_MEMORY_MODEL", "claude-haiku-4-5").strip()

MAX_OUTPUT_TOKENS = int(os.getenv("GRIOT_MAX_OUTPUT_TOKENS", "16000"))

# --- Storage -----------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = Path(os.getenv("GRIOT_DB_PATH", ROOT_DIR / "griot.db"))

# Turns of conversation history replayed to the model on each request. Bounded
# so a long thread cannot grow the request without limit.
HISTORY_TURNS = int(os.getenv("GRIOT_HISTORY_TURNS", "12"))

# Memory rows retrieved into the system prompt.
MEMORY_LIMIT = int(os.getenv("GRIOT_MEMORY_LIMIT", "8"))

# --- Security ----------------------------------------------------------------

# Shared secret required on every mutating request. Empty disables auth, which
# is only tolerable locally -- see is_serverless() below.
API_KEY = os.getenv("GRIOT_API_KEY", "").strip()

# --- Tenancy -----------------------------------------------------------------

# The tenant that rows written before multi-tenancy belong to, and the one a
# caller gets when it sends no X-Tenant-Id. Keeping the operator's own history
# under a named tenant rather than a null lets every query require a tenant_id
# with no special case for "no tenant".
INTERNAL_TENANT = os.getenv("GRIOT_INTERNAL_TENANT", "speakpower-internal").strip()

# A tenant id is an opaque slug minted by the caller (the Studio Worker). It is
# never shown to the model and never parsed for meaning -- it only has to be
# stable, comparable, and safe to store.
TENANT_ID_MAX_LENGTH = 64

# --- Environment -------------------------------------------------------------


def is_serverless() -> bool:
    """True when running on Vercel, where the filesystem is read-only."""
    return bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))


def model_ready() -> bool:
    return bool(ANTHROPIC_API_KEY)


def auth_enabled() -> bool:
    return bool(API_KEY)


class ConfigError(RuntimeError):
    """Raised when the process cannot serve safely with the current settings."""


def validate() -> None:
    """Fail fast on configurations that would break or leak in production.

    Called at startup. Raising here surfaces the problem in deployment logs
    rather than as a confusing 500 on the first real request.
    """
    if not is_serverless():
        return

    if not DATABASE_URL:
        raise ConfigError(
            "DATABASE_URL is required in a serverless deployment: the filesystem "
            "is read-only, so the SQLite fallback cannot persist. Provision "
            "Postgres and set DATABASE_URL (use the pooled connection string)."
        )

    if not API_KEY:
        raise ConfigError(
            "GRIOT_API_KEY is required in a serverless deployment. Without it "
            "every endpoint is open to anyone who finds the URL, including the "
            "ones that spend Claude credits."
        )
