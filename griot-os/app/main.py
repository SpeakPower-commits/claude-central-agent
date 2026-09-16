from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("GRIOT_DB_PATH", ROOT / "griot.db"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Claude model defaults. Override per-deployment with ANTHROPIC_MODEL.
DEFAULT_MODEL = "claude-opus-5"
MAX_OUTPUT_TOKENS = 16000

PROJECTS = {
    "speakpower": "Brand storytelling, communications, market development",
    "tonninyira": "Marketplace product, software, growth and operations",
    "cuepointe": "Community, tournament operations, brand and growth",
    "ubf": "Conservation communications and AI/process automation",
    "fob": "Biodiversity/community ecosystem and operations",
    "other": "Business analysis, brand strategy and project operations",
}
AGENTS = {
    "story": "StoryAgent",
    "market": "MarketAgent",
    "data": "DataAgent",
    "dev": "DevAgent",
    "research": "ResearchAgent",
    "growth": "GrowthAgent",
    "operations": "OperationsAgent",
    "brand": "BrandAgent",
    "strategy": "StrategyAgent",
}
STEPS = [
    "UNDERSTAND", "CONTEXT", "EVIDENCE", "DIAGNOSE", "OPTIONS",
    "RECOMMEND", "EXECUTE", "MEASURE", "LEARN",
]

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    project: str | None = None
    mode: str = "think"
    approved: bool = False

class MemoryRequest(BaseModel):
    project: str
    kind: str
    title: str
    content: str
    confidence: str = "inference"

class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool

app = FastAPI(title="GRIOT OS", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

SCHEMA_SQL = """
create table if not exists memories (
    id text primary key,
    project text not null,
    kind text not null,
    title text not null,
    content text not null,
    confidence text not null,
    created_at text not null
);
create table if not exists decisions (
    id text primary key,
    project text not null,
    request text not null,
    recommendation text not null,
    status text not null,
    created_at text not null
);
create table if not exists actions (
    id text primary key,
    project text not null,
    action_type text not null,
    payload text not null,
    status text not null,
    created_at text not null
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("DATABASE_URL is configured but psycopg is not installed")
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as db:
            for statement in SCHEMA_SQL.split(";"):
                if statement.strip():
                    db.execute(statement)
            db.commit()
        return

    with sqlite3.connect(DB_PATH) as db:
        db.executescript(SCHEMA_SQL)
        db.commit()


def fetch_memories(project: str | None = None, limit: int = 8) -> list[dict]:
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as db:
            if project:
                rows = db.execute(
                    "select * from memories where project in (%s, 'global') order by created_at desc limit %s",
                    (project, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "select * from memories order by created_at desc limit %s",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        if project:
            rows = db.execute(
                "select * from memories where project in (?, 'global') order by created_at desc limit ?",
                (project, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "select * from memories order by created_at desc limit ?",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def insert_row(table: str, values: tuple) -> None:
    columns = {
        "memories": "id, project, kind, title, content, confidence, created_at",
        "decisions": "id, project, request, recommendation, status, created_at",
        "actions": "id, project, action_type, payload, status, created_at",
    }[table]
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        placeholders = ",".join(["%s"] * len(values))
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(f"insert into {table} ({columns}) values ({placeholders})", values)
            db.commit()
        return

    placeholders = ",".join(["?"] * len(values))
    with sqlite3.connect(DB_PATH) as db:
        db.execute(f"insert into {table} ({columns}) values ({placeholders})", values)
        db.commit()


def update_action(action_id: str, status: str) -> bool:
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        with psycopg.connect(DATABASE_URL) as db:
            result = db.execute("update actions set status=%s where id=%s", (status, action_id))
            db.commit()
            return result.rowcount > 0

    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("update actions set status=? where id=?", (status, action_id))
        db.commit()
        return cur.rowcount > 0


def route(text: str) -> list[str]:
    t = text.lower()
    agents: list[str] = []
    if any(x in t for x in ["brand", "story", "copy", "campaign", "content", "audience"]):
        agents += ["story", "brand"]
    if any(x in t for x in ["market", "customer", "competitor", "growth", "sales", "revenue"]):
        agents += ["market", "growth"]
    if any(x in t for x in ["data", "kpi", "metric", "sql", "python", "analysis"]):
        agents += ["data"]
    if any(x in t for x in ["code", "github", "supabase", "bug", "app", "software", "api"]):
        agents += ["dev"]
    if any(x in t for x in ["research", "latest", "evidence", "trend"]):
        agents += ["research"]
    if any(x in t for x in ["process", "workflow", "sop", "automation", "operations"]):
        agents += ["operations"]
    if not agents:
        agents = ["strategy"]
    if "strategy" not in agents:
        agents.append("strategy")
    return list(dict.fromkeys(agents))


def build_system_prompt(req: ChatRequest, memories: list[dict], agents: list[str]) -> str:
    """Build the operator instruction: identity, protocol and retrieved memory.

    Kept separate from the user's request so the model receives a proper
    system/user split rather than one undifferentiated block.
    """
    project_context = PROJECTS.get(req.project or "other", "Cross-project strategic work")
    memory_text = "\n".join(
        f"- [{item['confidence']}] {item['title']}: {item['content']}" for item in memories
    ) or "- No stored memories retrieved."
    return f"""You are GRIOT OS, Thomas's strategic intelligence and execution agent.

MISSION: Think like a strategist. Validate like a data scientist. Build like a software engineer. Communicate like a storyteller. Operate like an owner.

PROJECT: {req.project or 'cross-project'}
CONTEXT: {project_context}
ACTIVE AGENTS: {', '.join(AGENTS[key] for key in agents)}
DECISION PROTOCOL: {' → '.join(STEPS)}

EVIDENCE DISCIPLINE: FACT, INFERENCE, HYPOTHESIS, RECOMMENDATION, UNKNOWN.
Never present an inference or hypothesis as a fact. Challenge weak assumptions. Never confuse activity with progress.

STORED MEMORY:
{memory_text}

Structure every response as:
1. Diagnosis
2. Evidence and unknowns
3. Recommendation
4. Next actions
5. Measurement
6. Approval requirement
"""


async def model(system_prompt: str, user_message: str) -> str:
    """Send one strategic-analysis turn to Claude and return the text response.

    Runs in orchestration-only mode when no API key is configured, so routing,
    memory and decision logging stay testable without spending tokens.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return (
            "GRIOT OS is running in orchestration-only mode. Add ANTHROPIC_API_KEY to enable model reasoning. "
            "Project routing, memory, decision logging and the interface are active."
        )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
            max_tokens=MAX_OUTPUT_TOKENS,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(401, "ANTHROPIC_API_KEY is invalid or revoked")
    except anthropic.PermissionDeniedError:
        raise HTTPException(403, "API key lacks permission for this model")
    except anthropic.NotFoundError:
        raise HTTPException(404, f"Unknown model: {os.getenv('ANTHROPIC_MODEL', DEFAULT_MODEL)}")
    except anthropic.RateLimitError as exc:
        retry_after = exc.response.headers.get("retry-after", "60")
        raise HTTPException(429, f"Rate limited by the Claude API. Retry after {retry_after}s.")
    except anthropic.APIStatusError as exc:
        raise HTTPException(502 if exc.status_code >= 500 else exc.status_code, exc.message)
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Could not reach the Claude API")

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        raise HTTPException(422, f"Claude declined this request (category: {category})")

    answer = "".join(block.text for block in response.content if block.type == "text").strip()
    if not answer:
        raise HTTPException(502, "Claude returned no text content")
    return answer


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": "GRIOT OS",
        "version": app.version,
        "memory": "postgres" if DATABASE_URL else "sqlite",
        "model": os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
        "model_ready": bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
    }


@app.get("/projects")
def projects():
    return PROJECTS


@app.get("/agents")
def agents():
    return AGENTS


@app.get("/memories")
def get_memories(project: str | None = None):
    return fetch_memories(project)


@app.post("/memory")
def create_memory(req: MemoryRequest):
    if req.project not in PROJECTS and req.project != "global":
        raise HTTPException(400, "Unknown project")
    item = {
        "id": str(uuid.uuid4()),
        "project": req.project,
        "kind": req.kind,
        "title": req.title,
        "content": req.content,
        "confidence": req.confidence,
        "created_at": now(),
    }
    insert_row("memories", tuple(item.values()))
    return item


@app.post("/chat")
@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.project and req.project not in PROJECTS:
        raise HTTPException(400, "Unknown project")
    selected_agents = route(req.message)
    memory = fetch_memories(req.project)
    answer = await model(build_system_prompt(req, memory, selected_agents), req.message)
    decision_id = str(uuid.uuid4())
    insert_row(
        "decisions",
        (
            decision_id,
            req.project or "global",
            req.message,
            answer[:5000],
            "analyzed",
            now(),
        ),
    )
    return {
        "decision_id": decision_id,
        "project": req.project,
        "mode": req.mode,
        "agents": [AGENTS[key] for key in selected_agents],
        "memory_used": len(memory),
        "answer": answer,
    }


@app.post("/approval")
@app.post("/api/approval")
def approval(req: ApprovalRequest):
    status = "approved" if req.approved else "rejected"
    if not update_action(req.action_id, status):
        raise HTTPException(404, "Action not found")
    return {"action_id": req.action_id, "status": status}


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")
