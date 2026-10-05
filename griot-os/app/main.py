"""GRIOT OS — strategic intelligence and execution agent.

FastAPI application: routing, request/response contracts and the chat flow.
Storage lives in db.py, Claude integration in llm.py, configuration in
config.py and authentication in security.py.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, llm
from .domain import AGENTS, PROJECT_NAMES, PROJECTS, STEPS
from .security import require_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("griot")

VERSION = "0.3.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate configuration at startup.

    Deliberately does no network or database work. On a serverless runtime this
    runs on every cold start, and anything that can block here blocks the first
    request behind it -- an unreachable database would turn into a function
    timeout rather than a diagnosable response. Schema setup happens lazily on
    first use instead (see db.init).
    """
    config.validate()
    logger.info(
        "GRIOT OS %s starting (memory=%s, model=%s, auth=%s)",
        VERSION, db.backend_name(), config.ANTHROPIC_MODEL, config.auth_enabled(),
    )
    yield


app = FastAPI(title="GRIOT OS", version=VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# --- Contracts ---------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    project: str | None = None
    thread_id: str | None = None
    mode: str = "think"


class ChatResponse(BaseModel):
    decision_id: str
    thread_id: str
    project: str | None
    mode: str
    agents: list[str]
    memory_used: int
    history_turns: int
    memory_written: str | None
    answer: str


class MemoryRequest(BaseModel):
    project: str
    kind: str
    title: str
    content: str
    confidence: str = "inference"


class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool


# --- Public routes -----------------------------------------------------------


@app.get("/health")
def health(check_db: bool = True):
    """Unauthenticated liveness probe. Reports configuration, never secrets.

    Pass ?check_db=false to skip the storage round trip when you only need to
    know the function itself is alive.
    """
    database_ready, database_error = (
        db.health() if check_db else (None, "not checked")
    )
    return {
        "status": "ok",
        "agent": "GRIOT OS",
        "version": VERSION,
        "memory": db.backend_name(),
        "database_ready": database_ready,
        "database_error": database_error,
        "model": config.ANTHROPIC_MODEL,
        "model_ready": config.model_ready(),
        "auth_enabled": config.auth_enabled(),
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Browsers request /favicon.ico at the root regardless of the link tags.

    vercel.json rewrites every path to this app, so without an explicit route
    that request would 404 against the API.
    """
    return FileResponse(
        config.STATIC_DIR / "brand" / "icon-32.png", media_type="image/png"
    )


@app.get("/")
def root():
    return FileResponse(config.STATIC_DIR / "index.html")


# --- Authenticated routes ----------------------------------------------------

protected = [Depends(require_api_key)]


@app.get("/projects", dependencies=protected)
def projects():
    """Projects this instance works across, with display names for the UI."""
    return {
        slug: {"name": PROJECT_NAMES[slug], "description": description}
        for slug, description in PROJECTS.items()
    }


@app.get("/agents", dependencies=protected)
def agents():
    return AGENTS


@app.get("/protocol", dependencies=protected)
def protocol():
    return {"steps": STEPS}


@app.get("/memories", dependencies=protected)
def get_memories(project: str | None = None):
    return db.fetch_memories(project)


@app.post("/memory", dependencies=protected)
def create_memory(req: MemoryRequest):
    if req.project not in PROJECTS and req.project != "global":
        raise HTTPException(400, "Unknown project")
    return db.insert_memory(
        req.project, req.kind, req.title, req.content, req.confidence
    )


@app.get("/threads/{thread_id}", dependencies=protected)
def get_thread(thread_id: str):
    history = db.fetch_history(thread_id, turns=100)
    if not history:
        raise HTTPException(404, "No such thread")
    return {"thread_id": thread_id, "messages": history}


@app.post("/chat", dependencies=protected, response_model=ChatResponse)
@app.post("/api/chat", dependencies=protected, response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """One pass of the decision protocol, within a durable conversation thread."""
    if req.project and req.project not in PROJECTS:
        raise HTTPException(400, "Unknown project")

    thread_id = req.thread_id or db.new_id()
    selected = llm.route(req.message)
    memories = db.fetch_memories(req.project)
    history = db.fetch_history(thread_id)

    answer = await llm.analyse(
        llm.build_system_prompt(req.project, memories, selected),
        history,
        req.message,
    )

    # Persist the exchange before anything optional, so a failure in memory
    # distillation can never cost the conversation itself.
    db.insert_message(thread_id, req.project, "user", req.message)
    db.insert_message(thread_id, req.project, "assistant", answer)

    decision_id = db.new_id()
    db.insert_decision(
        decision_id, thread_id, req.project or "global", req.message, answer
    )

    memory_written = None
    if answer != llm.ORCHESTRATION_ONLY_NOTICE:
        distilled = await llm.distil_memory(
            req.project or "global", req.message, answer
        )
        if distilled:
            db.insert_memory(
                req.project or "global",
                distilled["kind"],
                distilled["title"],
                distilled["content"],
                distilled["confidence"],
            )
            memory_written = distilled["title"]

    return ChatResponse(
        decision_id=decision_id,
        thread_id=thread_id,
        project=req.project,
        mode=req.mode,
        agents=[AGENTS[key] for key in selected],
        memory_used=len(memories),
        history_turns=len(history) // 2,
        memory_written=memory_written,
        answer=answer,
    )


@app.post("/approval", dependencies=protected)
@app.post("/api/approval", dependencies=protected)
def approval(req: ApprovalRequest):
    status = "approved" if req.approved else "rejected"
    if not db.update_action(req.action_id, status):
        raise HTTPException(404, "Action not found")
    return {"action_id": req.action_id, "status": status}
