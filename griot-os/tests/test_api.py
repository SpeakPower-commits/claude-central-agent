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


def test_health_advertises_tenancy_without_auth(client):
    # The SpeakPower Worker refuses to forward client traffic to a GRIOT that
    # does not report this, because a GRIOT without tenancy ignores
    # X-Tenant-Id and pools every client's memories together. It has to be
    # readable before authentication, since that is when the Worker checks.
    body = client.get("/health?check_db=false").json()
    assert body["tenancy"] is True
    assert body["tenant_header"] == "X-Tenant-Id"


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


# --- The client workspace ------------------------------------------------------
# Lenses chosen by the person asking, per-request bounds, and the
# conversations, decisions and memory deletion a front end shows each client.
# Every listing is tested from the other tenant's side as well.


def test_health_advertises_the_workspace(client):
    assert client.get("/health?check_db=false").json()["workspace"] is True


def test_chosen_lenses_replace_routing(client):
    r = client.post(
        "/chat",
        json={"message": "Write our donor story", "lenses": ["data", "market", "data"]},
        headers=TENANT_A,
    )
    assert r.status_code == 200
    # In the order chosen, each once; the router's "story" pick is not added.
    assert r.json()["agents"] == ["DataAgent", "MarketAgent"]


def test_unknown_or_too_many_lenses_are_refused(client):
    unknown = client.post("/chat", json={"message": "x", "lenses": ["data", "projects"]}, headers=TENANT_A)
    assert unknown.status_code == 400 and "projects" in unknown.json()["detail"]
    too_many = client.post(
        "/chat", json={"message": "x", "lenses": ["data", "market", "story", "brand"]}, headers=TENANT_A
    )
    assert too_many.status_code == 422


@pytest.mark.parametrize(
    "bounds",
    [{"effort": "extreme"}, {"max_output_tokens": 500}, {"max_output_tokens": 64000}],
)
def test_request_bounds_are_validated(client, bounds):
    r = client.post("/chat", json={"message": "x", **bounds}, headers=TENANT_A)
    assert r.status_code == 422


def test_request_bounds_reach_the_model_call(client, monkeypatch):
    seen = {}

    async def fake_analyse(system_prompt, history, user_message, effort=None, max_tokens=None):
        seen.update(effort=effort, max_tokens=max_tokens)
        return "FACT: bounded."

    monkeypatch.setattr(llm, "analyse", fake_analyse)
    r = client.post(
        "/chat",
        json={"message": "Bounded question", "effort": "medium", "max_output_tokens": 8000},
        headers=TENANT_A,
    )
    assert r.status_code == 200
    assert seen == {"effort": "medium", "max_tokens": 8000}


def test_analyse_sends_effort_caps_the_backstop_and_flags_a_cut_off_answer(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    calls = []

    class FakeMessages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason="max_tokens",
                content=[SimpleNamespace(type="text", text="FACT: the first half")],
            )

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(config, "MAX_OUTPUT_TOKENS", 6000)
    monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=FakeMessages()))

    answer = asyncio.run(llm.analyse("system", [], "question", effort="medium", max_tokens=8000))
    assert calls[0]["max_tokens"] == 6000, "never above GRIOT's own ceiling"
    assert calls[0]["extra_body"] == {"output_config": {"effort": "medium"}}
    assert answer.endswith(llm.CUT_SHORT_NOTE)

    asyncio.run(llm.analyse("system", [], "question"))
    assert calls[1]["max_tokens"] == 6000 and "extra_body" not in calls[1], "unchanged without bounds"


def test_threads_list_only_the_tenants_own_conversations(client):
    first = client.post("/chat", json={"message": "Alpha's pricing question"}, headers=TENANT_A).json()
    client.post(
        "/chat",
        json={"message": "and a follow-up", "thread_id": first["thread_id"]},
        headers=TENANT_A,
    )
    client.post("/chat", json={"message": "Beta's hiring question"}, headers=TENANT_B)

    a = client.get("/threads", headers=TENANT_A).json()
    mine = [t for t in a if t["thread_id"] == first["thread_id"]]
    assert len(mine) == 1
    assert mine[0]["first_question"] == "Alpha's pricing question"
    assert mine[0]["messages"] == 4  # two questions, two answers
    assert all("Beta" not in t["first_question"] for t in a)

    b_ids = {t["thread_id"] for t in client.get("/threads", headers=TENANT_B).json()}
    assert first["thread_id"] not in b_ids


def test_decisions_list_only_the_tenants_own(client):
    client.post("/chat", json={"message": "Alpha decision to log"}, headers=TENANT_A)
    a = [d["request"] for d in client.get("/decisions", headers=TENANT_A).json()]
    b = [d["request"] for d in client.get("/decisions", headers=TENANT_B).json()]
    assert "Alpha decision to log" in a
    assert "Alpha decision to log" not in b


def test_a_memory_can_be_deleted_only_by_its_own_tenant(client):
    created = client.post("/memory", json=_memory("global", "Alpha to delete"), headers=TENANT_A).json()

    assert client.delete(f"/memories/{created['id']}", headers=TENANT_B).status_code == 404
    assert "Alpha to delete" in [m["title"] for m in client.get("/memories", headers=TENANT_A).json()]

    assert client.delete(f"/memories/{created['id']}", headers=TENANT_A).status_code == 200
    assert "Alpha to delete" not in [m["title"] for m in client.get("/memories", headers=TENANT_A).json()]
    assert client.delete(f"/memories/{created['id']}", headers=TENANT_A).status_code == 404


def test_profile_memories_stay_in_every_turn(client, monkeypatch):
    tenant = {**AUTH, "X-Tenant-Id": "client-profile"}
    profile = {**_memory("global", "Who I am"), "kind": "profile",
               "content": "Head of Partnerships at Alpha"}
    client.post("/memory", json=profile, headers=tenant)
    client.post("/memory", json={**profile, "title": "Someone else"}, headers=TENANT_B)
    for i in range(config.MEMORY_LIMIT + 3):
        client.post("/memory", json=_memory("global", f"Later note {i}"), headers=tenant)

    seen = {}
    real = llm.build_system_prompt

    def spy(project, memories, agents, documents=None, **kwargs):
        seen["titles"] = [m["title"] for m in memories]
        return real(project, memories, agents, documents, **kwargs)

    monkeypatch.setattr(llm, "build_system_prompt", spy)
    r = client.post("/chat", json={"message": "What should I do first?"}, headers=tenant)
    assert r.status_code == 200
    # Pinned first, however many newer memories there are; never another tenant's.
    assert seen["titles"][0] == "Who I am"
    assert "Someone else" not in seen["titles"]
    assert len(seen["titles"]) == 1 + config.MEMORY_LIMIT
    assert r.json()["memory_used"] == 1 + config.MEMORY_LIMIT


def test_memories_listing_accepts_a_limit(client):
    tenant = {**AUTH, "X-Tenant-Id": "client-gamma"}
    for i in range(config.MEMORY_LIMIT + 4):
        client.post("/memory", json=_memory("global", f"Gamma {i}"), headers=tenant)
    assert len(client.get("/memories", headers=tenant).json()) == config.MEMORY_LIMIT
    assert len(client.get("/memories?limit=100", headers=tenant).json()) == config.MEMORY_LIMIT + 4
    assert len(client.get("/memories?limit=0", headers=tenant).json()) == config.MEMORY_LIMIT
    assert len(client.get("/memories?limit=1", headers=tenant).json()) == 1
    other = [m["title"] for m in client.get("/memories?limit=200", headers=TENANT_B).json()]
    assert not any(t.startswith("Gamma") for t in other)


def test_health_advertises_documents(client):
    assert client.get("/health?check_db=false").json()["documents"] is True


def test_document_excerpts_reach_the_prompt_with_their_sources(client, monkeypatch):
    seen = {}

    async def fake_analyse(system_prompt, history, user_message, effort=None, max_tokens=None):
        seen["prompt"] = system_prompt
        return "FACT: [Annual report 2025, p. 4] Enrolment rose."

    monkeypatch.setattr(llm, "analyse", fake_analyse)
    r = client.post(
        "/chat",
        json={"message": "How did enrolment do?", "context": [
            {"source": "Annual report 2025, p. 4", "text": "Enrolment rose 18% in 2025."},
            {"source": "Budget 2026", "text": "Teacher salaries are 61% of costs."},
        ]},
        headers=TENANT_A,
    )
    assert r.status_code == 200
    assert "CLIENT DOCUMENTS" in seen["prompt"]
    assert "- [Annual report 2025, p. 4] Enrolment rose 18% in 2025." in seen["prompt"]
    assert "cite its source in square brackets" in seen["prompt"]

    client.post("/chat", json={"message": "No documents this time"}, headers=TENANT_A)
    assert "CLIENT DOCUMENTS" not in seen["prompt"], "absent when none are sent"


@pytest.mark.parametrize(
    "context",
    [
        [{"source": "x", "text": "y"}] * 13,
        [{"source": "x", "text": "y" * 1201}],
        [{"source": "", "text": "y"}],
        [{"text": "no source"}],
    ],
)
def test_document_excerpts_are_bounded(client, context):
    r = client.post("/chat", json={"message": "x", "context": context}, headers=TENANT_A)
    assert r.status_code == 422


def test_health_advertises_answer_modes(client):
    assert client.get("/health?check_db=false").json()["modes"] is True


@pytest.mark.parametrize(
    "mode,heading,section",
    [
        ("challenge", "CHALLENGE", "five weakest assumptions"),
        ("diagnose", "DIAGNOSE", "Three likely root causes"),
        ("plan", "PLAN", "The first step to take this week"),
    ],
)
def test_answer_mode_reaches_the_prompt(client, monkeypatch, mode, heading, section):
    seen = {}

    async def fake_analyse(system_prompt, history, user_message, effort=None, max_tokens=None):
        seen["prompt"] = system_prompt
        seen["message"] = user_message
        return "RECOMMENDATION: Start small."

    monkeypatch.setattr(llm, "analyse", fake_analyse)
    r = client.post("/chat", json={"message": "Should we expand?", "answer_mode": mode}, headers=TENANT_A)
    assert r.status_code == 200
    assert "ANSWER MODE: " + heading in seen["prompt"]
    assert section in seen["prompt"]
    assert seen["message"] == "Should we expand?", "the question itself is never rewritten"

    client.post("/chat", json={"message": "And now?"}, headers=TENANT_A)
    assert "ANSWER MODE" not in seen["prompt"], "absent when no mode is chosen"


@pytest.mark.parametrize("mode", ["think", "CHALLENGE", "", "roast"])
def test_unknown_answer_modes_are_refused(client, mode):
    r = client.post("/chat", json={"message": "x", "answer_mode": mode}, headers=TENANT_A)
    assert r.status_code == 422


def test_workspace_reads_require_a_key(client):
    for path in ("/threads", "/decisions"):
        assert client.get(path).status_code == 401
    assert client.delete("/memories/anything").status_code == 401


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



# --- A client's own projects --------------------------------------------------
#
# Written from the other tenant's side as well: a client's project is theirs
# alone, and deleting one removes only what was filed under it.

import re  # noqa: E402

SLUG = re.compile(r"p-[0-9a-f]{8}")


def _new_project(client, headers, name):
    r = client.post("/tenant/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_advertises_client_projects(client):
    assert client.get("/health?check_db=false").json()["projects"] is True


def test_a_tenant_creates_and_lists_its_own_projects(client):
    tenant = {**AUTH, "X-Tenant-Id": "client-projects"}
    made = _new_project(client, tenant, "  Coffee   export pitch ")
    assert SLUG.fullmatch(made["slug"])
    assert made["name"] == "Coffee export pitch"

    mine = client.get("/tenant/projects", headers=tenant).json()
    assert [p["slug"] for p in mine] == [made["slug"]]
    theirs = client.get("/tenant/projects", headers=TENANT_B).json()
    assert made["slug"] not in [p["slug"] for p in theirs]
    # The operator's ventures are never listed as a client's projects.
    assert not any(p["slug"] in config_projects() for p in mine)


def config_projects():
    from app.domain import PROJECTS
    return set(PROJECTS)


def test_project_names_are_required_and_bounded(client):
    tenant = {**AUTH, "X-Tenant-Id": "client-names"}
    assert client.post("/tenant/projects", json={"name": "   "}, headers=tenant).status_code == 400
    assert client.post("/tenant/projects", json={"name": "x" * 61}, headers=tenant).status_code == 422
    assert client.post("/tenant/projects", json={}, headers=tenant).status_code == 422


def test_a_tenant_keeps_at_most_twenty_projects(client):
    tenant = {**AUTH, "X-Tenant-Id": "client-many"}
    for i in range(20):
        _new_project(client, tenant, f"Project {i}")
    r = client.post("/tenant/projects", json={"name": "One too many"}, headers=tenant)
    assert r.status_code == 409
    # Another tenant is unaffected.
    _new_project(client, {**AUTH, "X-Tenant-Id": "client-few"}, "First")


def test_chat_and_memory_accept_only_the_tenants_own_project(client):
    mine = _new_project(client, TENANT_A, "Alpha launch")["slug"]

    ok = client.post("/chat", json={"message": "Alpha project question", "project": mine}, headers=TENANT_A)
    assert ok.status_code == 200
    assert ok.json()["project"] == mine
    assert client.post("/memory", json=_memory(mine, "Alpha project fact"), headers=TENANT_A).status_code == 200

    # Holding another tenant's slug is not permission to use it.
    assert client.post("/chat", json={"message": "x", "project": mine}, headers=TENANT_B).status_code == 400
    assert client.post("/memory", json=_memory(mine, "Beta sneaks in"), headers=TENANT_B).status_code == 400
    # A made-up slug in the right shape is refused too.
    assert client.post("/chat", json={"message": "x", "project": "p-00000000"}, headers=TENANT_A).status_code == 400
    # 'global' stays available to everyone, within their own tenant.
    assert client.post("/chat", json={"message": "Alpha global question", "project": "global"}, headers=TENANT_A).status_code == 200


def test_the_prompt_names_the_clients_project_not_its_slug(client, monkeypatch):
    mine = _new_project(client, TENANT_A, "Donor pitch 2027")["slug"]
    seen = {}
    real = llm.build_system_prompt

    def spy(*args, **kwargs):
        seen["prompt"] = real(*args, **kwargs)
        return seen["prompt"]

    monkeypatch.setattr(llm, "build_system_prompt", spy)
    client.post("/chat", json={"message": "Where do we start?", "project": mine}, headers=TENANT_A)
    assert '"Donor pitch 2027" (the client\'s own project)' in seen["prompt"]
    assert mine not in seen["prompt"]


def test_threads_and_decisions_filter_by_project(client):
    tenant = {**AUTH, "X-Tenant-Id": "client-filter"}
    p1 = _new_project(client, tenant, "One")["slug"]
    in_p1 = client.post("/chat", json={"message": "Filed under one", "project": p1}, headers=tenant).json()
    in_global = client.post("/chat", json={"message": "Filed nowhere in particular"}, headers=tenant).json()

    threads = client.get(f"/threads?project={p1}", headers=tenant).json()
    assert [t["thread_id"] for t in threads] == [in_p1["thread_id"]]
    assert threads[0]["project"] == p1
    general = client.get("/threads?project=global", headers=tenant).json()
    assert [t["thread_id"] for t in general] == [in_global["thread_id"]]
    assert general[0]["project"] == "global"
    assert len(client.get("/threads", headers=tenant).json()) == 2

    decisions = client.get(f"/decisions?project={p1}", headers=tenant).json()
    assert [d["request"] for d in decisions] == ["Filed under one"]
    assert [d["request"] for d in client.get("/decisions?project=global", headers=tenant).json()] == [
        "Filed nowhere in particular"
    ]
    # Another tenant filtering by this slug sees nothing.
    assert client.get(f"/threads?project={p1}", headers=TENANT_B).json() == []
    assert client.get(f"/decisions?project={p1}", headers=TENANT_B).json() == []


def test_only_the_owner_can_rename_a_project(client):
    slug = _new_project(client, TENANT_A, "Old name")["slug"]
    assert client.patch(f"/tenant/projects/{slug}", json={"name": "Taken"}, headers=TENANT_B).status_code == 404
    r = client.patch(f"/tenant/projects/{slug}", json={"name": " New   name "}, headers=TENANT_A)
    assert r.status_code == 200 and r.json()["name"] == "New name"
    assert client.patch("/tenant/projects/p-00000000", json={"name": "x"}, headers=TENANT_A).status_code == 404


def test_deleting_a_project_removes_only_what_was_filed_under_it(client):
    tenant = {**AUTH, "X-Tenant-Id": "client-delete"}
    keep = _new_project(client, tenant, "Keep")["slug"]
    drop = _new_project(client, tenant, "Drop")["slug"]
    for slug in (keep, drop):
        client.post("/chat", json={"message": f"Question in {slug}", "project": slug}, headers=tenant)
        client.post("/memory", json=_memory(slug, f"Fact in {slug}"), headers=tenant)
    client.post("/memory", json=_memory("global", "General fact"), headers=tenant)
    dropped_thread = client.get(f"/threads?project={drop}", headers=tenant).json()[0]["thread_id"]
    # Another tenant's row filed under the same slug (slugs are only unique
    # within a tenant) must survive this tenant's delete.
    from app import db
    db.insert_memory("client-other", drop, "fact", "Other tenant, same slug", "body", "fact")

    # Not another tenant's to delete.
    assert client.delete(f"/tenant/projects/{drop}", headers=TENANT_B).status_code == 404
    assert client.get(f"/threads?project={drop}", headers=tenant).json() != []

    assert client.delete(f"/tenant/projects/{drop}", headers=tenant).status_code == 200
    assert client.delete(f"/tenant/projects/{drop}", headers=tenant).status_code == 404
    assert [p["slug"] for p in client.get("/tenant/projects", headers=tenant).json()] == [keep]

    assert client.get(f"/threads?project={drop}", headers=tenant).json() == []
    assert client.get(f"/decisions?project={drop}", headers=tenant).json() == []
    assert client.get(f"/threads/{dropped_thread}", headers=tenant).status_code == 404
    titles = [m["title"] for m in client.get("/memories?limit=200", headers=tenant).json()]
    assert f"Fact in {drop}" not in titles
    assert f"Fact in {keep}" in titles and "General fact" in titles
    assert len(client.get(f"/threads?project={keep}", headers=tenant).json()) == 1
    assert [m["title"] for m in db.fetch_memories("client-other", drop)] == ["Other tenant, same slug"]
    # Once deleted, the slug can no longer be used.
    assert client.post("/chat", json={"message": "x", "project": drop}, headers=tenant).status_code == 400


def test_studio_page_is_served_without_a_key(client):
    """The video editor is public: it never calls the API, so it needs no key."""
    response = client.get("/studio")
    assert response.status_code == 200
    assert "SpeakPower Studio" in response.text
    assert "/static/studio/app.js" in response.text


@pytest.mark.parametrize("path", [
    "/static/studio/app.js",
    "/static/studio/project.js",
    "/static/studio/renderer.js",
    "/static/studio/timeline.js",
    "/static/studio/exporter.js",
    "/static/studio/studio.css",
    "/static/studio/fonts/Inter-Black.otf",
    "/static/studio/fonts/Inter-ExtraBold.otf",
    "/static/studio/fonts/OFL.txt",
    "/static/studio/brand/speakpower-badge.png",
])
def test_studio_assets_are_served(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    # Vercel functions cap a response at 4.5 MB, and these are served through
    # the function, so any asset over that would 500 in production.
    assert len(response.content) < 4_500_000, path


def test_griot_links_to_the_studio(client):
    assert 'href="/studio"' in client.get("/").text
