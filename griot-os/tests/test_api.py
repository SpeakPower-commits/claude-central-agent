"""Smoke tests for the GRIOT OS API.

Run: pytest -q   (from the griot-os directory)

These cover the contracts most likely to break silently in a refactor:
authentication, thread continuity, routing, and the startup guards that keep
an unsafe configuration out of production.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_KEY = "test-key"
os.environ["GRIOT_API_KEY"] = API_KEY
os.environ["GRIOT_DB_PATH"] = str(Path(tempfile.gettempdir()) / "griot-test.db")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import config, llm  # noqa: E402
from app.main import app  # noqa: E402

AUTH = {"X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def client():
    db_path = Path(os.environ["GRIOT_DB_PATH"])
    db_path.unlink(missing_ok=True)
    with TestClient(app) as c:
        yield c
    db_path.unlink(missing_ok=True)


# --- Health ------------------------------------------------------------------


def test_health_is_public_and_reports_state(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database_ready"] is True
    assert body["auth_enabled"] is True


# --- Authentication ----------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_chat_rejects_bad_credentials(client, headers):
    r = client.post("/chat", json={"message": "hi"}, headers=headers)
    assert r.status_code == 401


def test_protected_reads_require_a_key(client):
    assert client.get("/memories").status_code == 401
    assert client.get("/memories", headers=AUTH).status_code == 200


# --- Chat and threads --------------------------------------------------------


def test_chat_starts_a_thread_and_remembers_it(client):
    first = client.post(
        "/chat", json={"message": "Diagnose growth", "project": "tonninyira"}, headers=AUTH
    ).json()
    assert first["history_turns"] == 0
    thread_id = first["thread_id"]

    second = client.post(
        "/chat",
        json={"message": "Say more", "project": "tonninyira", "thread_id": thread_id},
        headers=AUTH,
    ).json()

    assert second["thread_id"] == thread_id
    assert second["history_turns"] == 1

    stored = client.get(f"/threads/{thread_id}", headers=AUTH).json()
    assert [m["role"] for m in stored["messages"]] == [
        "user", "assistant", "user", "assistant"
    ]


def test_unknown_project_is_rejected(client):
    r = client.post("/chat", json={"message": "x", "project": "nope"}, headers=AUTH)
    assert r.status_code == 400


def test_empty_message_is_rejected(client):
    r = client.post("/chat", json={"message": ""}, headers=AUTH)
    assert r.status_code == 422


def test_missing_thread_returns_404(client):
    assert client.get("/threads/does-not-exist", headers=AUTH).status_code == 404


# --- Memory ------------------------------------------------------------------


def test_memory_round_trip(client):
    created = client.post(
        "/memory",
        json={
            "project": "tonninyira",
            "kind": "constraint",
            "title": "Small engineering capacity",
            "content": "One part-time engineer through Q3.",
            "confidence": "fact",
        },
        headers=AUTH,
    ).json()
    assert created["id"]

    titles = [m["title"] for m in client.get(
        "/memories?project=tonninyira", headers=AUTH
    ).json()]
    assert "Small engineering capacity" in titles


# --- Routing -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected,forbidden",
    [
        # "app" is a substring of "happy" -- the old substring matcher sent this
        # to DevAgent.
        ("How do I make our customers happy?", "market", "dev"),
        ("apply for a grant", "strategy", "dev"),
        ("fix the deployment API bug", "dev", None),
        ("write a campaign for our audience", "story", None),
    ],
)
def test_routing_word_boundaries(text, expected, forbidden):
    agents = llm.route(text)
    assert expected in agents
    if forbidden:
        assert forbidden not in agents


def test_strategy_is_always_present():
    assert "strategy" in llm.route("anything at all")


# --- Startup guards ----------------------------------------------------------


def test_serverless_requires_database(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "API_KEY", "set")
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(config.ConfigError, match="DATABASE_URL"):
        config.validate()


def test_serverless_requires_api_key(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgres://x")
    monkeypatch.setattr(config, "API_KEY", "")
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(config.ConfigError, match="GRIOT_API_KEY"):
        config.validate()
