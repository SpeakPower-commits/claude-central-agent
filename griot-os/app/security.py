"""Request authentication and tenant resolution.

A single shared secret, compared in constant time, sent as the X-API-Key
header. That is the right weight for a *trusted caller*: the key is held by the
SpeakPower Studio Worker and used server-to-server, never shipped to a browser.

Because the key authenticates the caller rather than the end user, the tenant
arrives alongside it in X-Tenant-Id. That header is only as trustworthy as the
key -- anyone holding the key could name any tenant -- which is precisely why
the key must stay server-side. The Worker maps a signed-in person to a tenant
id; GRIOT trusts it to have done so, and isolates on the result.

config.validate() refuses to start a serverless deployment with no key set, so
the open-by-default path cannot reach production.
"""

from __future__ import annotations

import re
import secrets

from fastapi import Header, HTTPException

from . import config

API_KEY_HEADER = "X-API-Key"
TENANT_HEADER = "X-Tenant-Id"

# Mirrors db._SAFE_TENANT. Duplicated on purpose: this one rejects a request,
# that one guards DDL, and neither should start depending on the other.
_TENANT_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,%d}" % (config.TENANT_ID_MAX_LENGTH - 1)
)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency guarding every route that reads or spends.

    No-ops when no key is configured, which only happens locally: a serverless
    boot without GRIOT_API_KEY fails at startup instead.
    """
    if not config.auth_enabled():
        return

    if not x_api_key or not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


async def resolve_tenant(
    x_tenant_id: str | None = Header(default=None),
) -> str:
    """FastAPI dependency returning the tenant every query will be scoped to.

    Absent header -> the internal tenant. That keeps the operator's own use of
    GRIOT working unchanged after this migration, and it is the same tenant the
    pre-tenancy rows were backfilled to.

    A malformed id is rejected rather than coerced: silently normalising it
    would let two different ids collapse onto one tenant's data, which is the
    one failure this whole layer exists to prevent.
    """
    if x_tenant_id is None:
        return config.INTERNAL_TENANT

    candidate = x_tenant_id.strip()
    if not _TENANT_PATTERN.fullmatch(candidate):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{TENANT_HEADER} must be 1-{config.TENANT_ID_MAX_LENGTH} characters "
                "of letters, digits, dot, underscore or hyphen, starting with a "
                "letter or digit."
            ),
        )
    return candidate
