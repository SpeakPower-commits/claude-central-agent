"""Storage layer.

Presents one API over two backends: Postgres in production, SQLite locally.
Callers never branch on the backend; this module owns that decision.

Connections are pooled. The previous implementation opened a fresh connection
per statement, which on a serverless runtime against a managed Postgres means
a TCP + TLS + auth round trip on every query and, under any concurrency,
connection exhaustion.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import config

try:
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only in trimmed installs
    ConnectionPool = None
    dict_row = None


SCHEMA_SQL = [
    """
    create table if not exists memories (
        id text primary key,
        project text not null,
        kind text not null,
        title text not null,
        content text not null,
        confidence text not null,
        created_at text not null
    )
    """,
    """
    create table if not exists decisions (
        id text primary key,
        thread_id text,
        project text not null,
        request text not null,
        recommendation text not null,
        status text not null,
        created_at text not null
    )
    """,
    """
    create table if not exists actions (
        id text primary key,
        project text not null,
        action_type text not null,
        payload text not null,
        status text not null,
        created_at text not null
    )
    """,
    """
    create table if not exists messages (
        id text primary key,
        thread_id text not null,
        project text,
        role text not null,
        content text not null,
        created_at text not null
    )
    """,
    "create index if not exists idx_messages_thread on messages (thread_id, created_at)",
    "create index if not exists idx_memories_project on memories (project, created_at)",
]

_pool: Any = None
_pool_lock = threading.Lock()
_initialised = False


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def using_postgres() -> bool:
    return bool(config.DATABASE_URL)


def backend_name() -> str:
    return "postgres" if using_postgres() else "sqlite"


def _get_pool():
    """Lazily build the Postgres pool, once per process.

    min_size is 0 so a cold serverless instance that never touches the database
    pays nothing, and max_size is small because each instance serves few
    concurrent requests -- the ceiling that matters is the provider's, shared
    across all warm instances.
    """
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            if ConnectionPool is None:
                raise RuntimeError(
                    "DATABASE_URL is set but psycopg_pool is not installed"
                )
            _pool = ConnectionPool(
                conninfo=config.DATABASE_URL,
                min_size=0,
                max_size=4,
                timeout=10,
                max_idle=300,
                kwargs={"row_factory": dict_row},
                open=True,
            )
    return _pool


@contextmanager
def connection() -> Iterator[Any]:
    """Yield a connection from the active backend."""
    if using_postgres():
        with _get_pool().connection() as conn:
            yield conn
        return

    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _sql(statement: str) -> str:
    """Translate placeholder style for the active backend.

    Statements are written with the SQLite '?' marker; Postgres wants '%s'.
    """
    return statement.replace("?", "%s") if using_postgres() else statement


def execute(statement: str, params: tuple = ()) -> int:
    """Run a write. Returns the affected row count."""
    with connection() as conn:
        cur = conn.execute(_sql(statement), params)
        if using_postgres():
            conn.commit()
        return cur.rowcount


def query(statement: str, params: tuple = ()) -> list[dict]:
    """Run a read. Returns rows as plain dicts."""
    with connection() as conn:
        cur = conn.execute(_sql(statement), params)
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def init() -> None:
    """Create tables if absent. Runs once per process, not once per request."""
    global _initialised
    if _initialised:
        return
    with _pool_lock:
        if _initialised:
            return
        with connection() as conn:
            for statement in SCHEMA_SQL:
                conn.execute(statement)
            if using_postgres():
                conn.commit()
        _initialised = True


def health() -> bool:
    """True when the datastore answers. Used by the health probe."""
    try:
        query("select 1 as ok")
        return True
    except Exception:
        return False


# --- Domain helpers ----------------------------------------------------------


def fetch_memories(project: str | None = None, limit: int | None = None) -> list[dict]:
    limit = limit or config.MEMORY_LIMIT
    if project:
        return query(
            "select * from memories where project in (?, 'global') "
            "order by created_at desc limit ?",
            (project, limit),
        )
    return query(
        "select * from memories order by created_at desc limit ?", (limit,)
    )


def insert_memory(
    project: str, kind: str, title: str, content: str, confidence: str
) -> dict:
    row = {
        "id": new_id(),
        "project": project,
        "kind": kind,
        "title": title,
        "content": content,
        "confidence": confidence,
        "created_at": now(),
    }
    execute(
        "insert into memories (id, project, kind, title, content, confidence, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?)",
        tuple(row[k] for k in
              ("id", "project", "kind", "title", "content", "confidence", "created_at")),
    )
    return row


def fetch_history(thread_id: str, turns: int | None = None) -> list[dict]:
    """Return the most recent messages for a thread, oldest first."""
    turns = turns or config.HISTORY_TURNS
    rows = query(
        "select role, content, created_at from messages where thread_id = ? "
        "order by created_at desc limit ?",
        (thread_id, turns * 2),
    )
    return list(reversed(rows))


def insert_message(thread_id: str, project: str | None, role: str, content: str) -> None:
    execute(
        "insert into messages (id, thread_id, project, role, content, created_at) "
        "values (?, ?, ?, ?, ?, ?)",
        (new_id(), thread_id, project, role, content, now()),
    )


def insert_decision(
    decision_id: str, thread_id: str, project: str, request: str, recommendation: str
) -> None:
    execute(
        "insert into decisions (id, thread_id, project, request, recommendation, status, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?)",
        (decision_id, thread_id, project, request, recommendation[:5000], "analyzed", now()),
    )


def update_action(action_id: str, status: str) -> bool:
    return execute(
        "update actions set status = ? where id = ?", (status, action_id)
    ) > 0
