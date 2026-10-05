"""Storage layer.

Presents one API over two backends: Postgres in production, SQLite locally.
Callers never branch on the backend; this module owns that decision.

Connections are short-lived and pooled *server-side* by Neon's PgBouncer
endpoint, not by a client-side pool.

That is deliberate. A client-side `psycopg_pool.ConnectionPool` runs background
worker threads, and this process is frozen between invocations on a serverless
runtime: threads that outlive the handler can leave an invocation that never
completes, which surfaces as a function timeout rather than an error. Pointing
DATABASE_URL at the pooled endpoint gets the pooling without that hazard.

Every connection carries an explicit connect timeout so an unreachable database
fails in seconds with a clear message instead of hanging until the platform
kills the function.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import config

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only in trimmed installs
    psycopg = None
    dict_row = None


# Every row belongs to exactly one tenant. No helper in this module reads or
# writes a domain table without one.
TENANT_TABLES = ("memories", "decisions", "actions", "messages")

# Slug charset for a tenant id. Applied to the migration default below, and to
# every inbound id in security.resolve_tenant().
_SAFE_TENANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

SCHEMA_SQL = [
    """
    create table if not exists memories (
        id text primary key,
        tenant_id text not null,
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
        tenant_id text not null,
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
        tenant_id text not null,
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
        tenant_id text not null,
        thread_id text not null,
        project text,
        role text not null,
        content text not null,
        created_at text not null
    )
    """,
]

# Indexes are applied separately, and strictly after _add_tenant_column: every
# one of them leads with tenant_id, so on a database created before tenancy the
# column has to exist first. Running them inside SCHEMA_SQL fails with
# "no such column: tenant_id" on exactly the upgrade path that matters.
INDEX_SQL = [
    # tenant_id leads every index because it leads every where-clause.
    "create index if not exists idx_messages_tenant_thread "
    "on messages (tenant_id, thread_id, created_at)",
    "create index if not exists idx_memories_tenant_project "
    "on memories (tenant_id, project, created_at)",
    "create index if not exists idx_decisions_tenant "
    "on decisions (tenant_id, created_at)",
]

_init_lock = threading.Lock()
_initialised = False

# Seconds to wait for a database connection before giving up. Short on purpose:
# a cold start that cannot reach Postgres should report that quickly, not sit
# until the platform's function timeout.
CONNECT_TIMEOUT = 8


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def using_postgres() -> bool:
    return bool(config.DATABASE_URL)


def backend_name() -> str:
    return "postgres" if using_postgres() else "sqlite"


@contextmanager
def connection() -> Iterator[Any]:
    """Yield a connection to the active backend, closing it afterwards."""
    if using_postgres():
        if psycopg is None:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed")
        conn = psycopg.connect(
            config.DATABASE_URL,
            connect_timeout=CONNECT_TIMEOUT,
            row_factory=dict_row,
        )
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
        return

    conn = sqlite3.connect(config.SQLITE_PATH, timeout=CONNECT_TIMEOUT)
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
    init()
    with connection() as conn:
        return conn.execute(_sql(statement), params).rowcount


def query(statement: str, params: tuple = ()) -> list[dict]:
    """Run a read. Returns rows as plain dicts."""
    init()
    with connection() as conn:
        rows = conn.execute(_sql(statement), params).fetchall()
    return [dict(row) for row in rows]


def init() -> None:
    """Create tables if absent. Runs once per process, not once per request.

    Called lazily from the first query rather than at startup: a serverless
    cold start should not block on schema work before it can answer anything,
    and /health must stay answerable even when the database is unreachable.
    """
    global _initialised
    if _initialised:
        return
    with _init_lock:
        if _initialised:
            return
        with connection() as conn:
            for statement in SCHEMA_SQL:
                conn.execute(statement)
            _add_tenant_column(conn)
            for statement in INDEX_SQL:
                conn.execute(statement)
        _initialised = True


def _existing_columns(conn: Any, table: str) -> set[str]:
    """Column names on `table`, asked of whichever backend is active.

    Introspection rather than try/except around ALTER: a swallowed exception
    would hide a real migration failure as readily as a duplicate column, and
    the two drivers raise different types for it.
    """
    if using_postgres():
        # Scoped to the connection's own schema: information_schema spans every
        # schema the role can see, so an unqualified table_name match could
        # find a same-named table elsewhere and skip a migration that is due.
        rows = conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = current_schema() and table_name = %s",
            (table,),
        ).fetchall()
        return {dict(row)["column_name"] for row in rows}

    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return {dict(row)["name"] for row in rows}


def _add_tenant_column(conn: Any) -> None:
    """Add tenant_id to tables created before multi-tenancy, and backfill.

    `create table if not exists` is a no-op on an existing table, so a
    deployment that already holds the operator's history would otherwise keep
    the old shape and fail every insert. The DEFAULT on the ALTER backfills
    every existing row to the internal tenant in one statement, which is what
    keeps that history reachable.

    Idempotent: once the column exists this does nothing.
    """
    # DDL takes no bound parameters in either backend, so the default is
    # interpolated. It comes from an operator-set env var rather than a
    # request, but interpolated SQL gets a charset guard regardless -- and the
    # guard doubles as a typo check on GRIOT_INTERNAL_TENANT.
    if not _SAFE_TENANT.fullmatch(config.INTERNAL_TENANT):
        raise ValueError(
            "GRIOT_INTERNAL_TENANT must match "
            f"{_SAFE_TENANT.pattern} (got {config.INTERNAL_TENANT!r})"
        )

    for table in TENANT_TABLES:
        if "tenant_id" in _existing_columns(conn, table):
            continue
        conn.execute(
            f"alter table {table} add column tenant_id text not null "
            f"default '{config.INTERNAL_TENANT}'"
        )


def health() -> tuple[bool, str | None]:
    """Report whether the datastore answers, and why not when it does not.

    Never raises: the probe has to stay useful precisely when storage is the
    thing that is broken.
    """
    try:
        with connection() as conn:
            conn.execute("select 1")
        return True, None
    except Exception as exc:  # noqa: BLE001 - surfaced as diagnostic text
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


# --- Domain helpers ----------------------------------------------------------


def fetch_memories(
    tenant_id: str, project: str | None = None, limit: int | None = None
) -> list[dict]:
    """Memories visible to one tenant.

    'global' is a project within a tenant, not across tenants -- the tenant
    filter applies to it like any other row.
    """
    limit = limit or config.MEMORY_LIMIT
    if project:
        return query(
            "select * from memories where tenant_id = ? and project in (?, 'global') "
            "order by created_at desc limit ?",
            (tenant_id, project, limit),
        )
    return query(
        "select * from memories where tenant_id = ? "
        "order by created_at desc limit ?",
        (tenant_id, limit),
    )


def insert_memory(
    tenant_id: str, project: str, kind: str, title: str, content: str, confidence: str
) -> dict:
    row = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "project": project,
        "kind": kind,
        "title": title,
        "content": content,
        "confidence": confidence,
        "created_at": now(),
    }
    execute(
        "insert into memories "
        "(id, tenant_id, project, kind, title, content, confidence, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?, ?)",
        tuple(row[k] for k in
              ("id", "tenant_id", "project", "kind", "title", "content",
               "confidence", "created_at")),
    )
    return row


def fetch_history(
    tenant_id: str, thread_id: str, turns: int | None = None
) -> list[dict]:
    """Return the most recent messages for a thread, oldest first.

    Scoped by tenant as well as thread: a thread id is a UUID, but guessing is
    not the only way to come by one, and an id is not an authorisation.
    """
    turns = turns or config.HISTORY_TURNS
    rows = query(
        "select role, content, created_at from messages "
        "where tenant_id = ? and thread_id = ? "
        "order by created_at desc limit ?",
        (tenant_id, thread_id, turns * 2),
    )
    return list(reversed(rows))


def insert_message(
    tenant_id: str, thread_id: str, project: str | None, role: str, content: str
) -> None:
    execute(
        "insert into messages "
        "(id, tenant_id, thread_id, project, role, content, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?)",
        (new_id(), tenant_id, thread_id, project, role, content, now()),
    )


def insert_decision(
    tenant_id: str, decision_id: str, thread_id: str, project: str,
    request: str, recommendation: str,
) -> None:
    execute(
        "insert into decisions "
        "(id, tenant_id, thread_id, project, request, recommendation, status, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?, ?)",
        (decision_id, tenant_id, thread_id, project, request,
         recommendation[:5000], "analyzed", now()),
    )


def update_action(tenant_id: str, action_id: str, status: str) -> bool:
    """Returns False for another tenant's action id, exactly as for an unknown
    one -- the caller cannot tell the two apart, which is the point."""
    return execute(
        "update actions set status = ? where id = ? and tenant_id = ?",
        (status, action_id, tenant_id),
    ) > 0
