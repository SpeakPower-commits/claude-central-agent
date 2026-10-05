"""Request authentication.

A single shared secret, compared in constant time, sent as the X-API-Key
header. That is the right weight for a single-operator tool: it keeps the
deployment off the open internet without standing up user accounts.

config.validate() refuses to start a serverless deployment with no key set,
so the open-by-default path cannot reach production.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from . import config

API_KEY_HEADER = "X-API-Key"


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
