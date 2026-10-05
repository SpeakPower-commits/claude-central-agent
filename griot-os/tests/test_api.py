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


# --- Tenancy -----------------------------------------------------------------
#
# The isolation tests are written adversarially: each one asserts that a tenant
# CANNOT see something, because a scoping bug shows up as silent over-sharing
# rather than as an error.

TENANT_A = {**AUTH, "X-Tenant-Id": "client-alpha"}
TENANT_B = {**AUTH, "X-Tenant-Id": "client-beta"}


def _memory(project: str, title: str) -> dict:
    return {
        "project": project,
        "kind": "constraint",
        "title": title,
        "content": "Written by one tenant only.",
        "confidence": "fact",
    }


def test_memories_do_not_leak_between_tenants(client):
    client.post("/memory", json=_memory("tonninyira", "Alpha only"), headers=TENANT_A)
    client.post("/memory", json=_memory("tonninyira", "Beta only"), headers=TENANT_B)

    a_titles = [m["title"] for m in client.get("/memories", headers=TENANT_A).json()]
    b_titles = [m["title"] for m in client.get("/memories", headers=TENANT_B).json()]

    assert "Alpha only" in a_titles and "Beta only" not in a_titles
    assert "Beta only" in b_titles and "Alpha only" not in b_titles


def test_global_project_is_scoped_per_tenant(client):
    """'global' is global within a tenant, not across them."""
    client.post("/memory", json=_memory("global", "Alpha global"), headers=TENANT_A)

    b_titles = [m["title"] for m in client.get(
        "/memories?project=tonninyira", headers=TENANT_B
    ).json()]
    assert "Alpha global" not in b_titles


def test_a_thread_id_is_not_an_authorisation(client):
    """Holding another tenant's thread id must not reveal the thread."""
    created = client.post(
        "/chat", json={"message": "Alpha's private question"}, headers=TENANT_A
    ).json()
    thread_id = created["thread_id"]

    assert client.get(f"/threads/{thread_id}", headers=TENANT_A).status_code == 200
    assert client.get(f"/threads/{thread_id}", headers=TENANT_B).status_code == 404


def test_history_does_not_cross_tenants(client):
    """Reusing another tenant's thread id must not replay their history."""
    first = client.post(
        "/chat", json={"message": "Alpha turn one"}, headers=TENANT_A
    ).json()
    client.post(
        "/chat",
        json={"message": "Alpha turn two", "thread_id": first["thread_id"]},
        headers=TENANT_A,
    )

    intruder = client.post(
        "/chat",
        json={"message": "Beta on Alpha's thread", "thread_id": first["thread_id"]},
        headers=TENANT_B,
    ).json()
    assert intruder["history_turns"] == 0


def test_approval_of_another_tenants_action_is_not_found(client):
    from app import db

    action_id = db.new_id()
    db.execute(
        "insert into actions "
        "(id, tenant_id, project, action_type, payload, status, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?)",
        (action_id, "client-alpha", "tonninyira", "publish", "{}", "pending", db.now()),
    )

    assert client.post(
        "/approval", json={"action_id": action_id, "approved": True}, headers=TENANT_B
    ).status_code == 404
    assert client.post(
        "/approval", json={"action_id": action_id, "approved": True}, headers=TENANT_A
    ).status_code == 200


def test_no_tenant_header_falls_back_to_the_internal_tenant(client):
    """The operator's own existing usage keeps working, unchanged."""
    client.post("/memory", json=_memory("speakpower", "Operator note"), headers=AUTH)

    assert "Operator note" in [
        m["title"] for m in client.get("/memories", headers=AUTH).json()
    ]
    assert "Operator note" not in [
        m["title"] for m in client.get("/memories", headers=TENANT_A).json()
    ]


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "-leading-hyphen", "has space", "has/slash", "a" * 65, "'; drop table--"],
)
def test_malformed_tenant_ids_are_rejected_not_coerced(client, bad):
    r = client.get("/memories", headers={**AUTH, "X-Tenant-Id": bad})
    assert r.status_code == 400


# --- Migration ---------------------------------------------------------------


def test_pre_tenancy_rows_are_backfilled(tmp_path, monkeypatch):
    """A database created before tenancy must keep its history, not lose it.

    `create table if not exists` is a no-op on an existing table, so without
    the ALTER this row would be stranded under a column that never arrives.
    """
    import sqlite3

    from app import db

    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.execute(
        "create table memories (id text primary key, project text not null, "
        "kind text not null, title text not null, content text not null, "
        "confidence text not null, created_at text not null)"
    )
    conn.execute(
        "insert into memories values ('old-1', 'speakpower', 'fact', "
        "'Written before tenancy', 'body', 'fact', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "SQLITE_PATH", legacy)
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(db, "_initialised", False)

    rows = db.fetch_memories(config.INTERNAL_TENANT)

    assert [r["title"] for r in rows] == ["Written before tenancy"]
    assert rows[0]["tenant_id"] == config.INTERNAL_TENANT
    assert db.fetch_memories("client-alpha") == []
