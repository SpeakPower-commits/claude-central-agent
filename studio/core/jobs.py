"""Job state for SpeakPower Studio.

One job is one video going through the pipeline. State lives in a JSON file in
the job's own folder, beside its outputs, so a restart of the server does not
lose the record of what was produced -- and so you can see what happened by
opening a file, without a database to inspect.

A lock guards writes because the worker thread and the web request handling the
browser's polling touch the same file.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from . import config

_WRITE_LOCK = threading.Lock()

# The pipeline, in order. The interface turns these into the progress list, so
# the names are user-facing: keep them plain.
STAGES: tuple[str, ...] = (
    "Fetching the video",
    "Listening to the audio",
    "Choosing the moments",
    "Cleaning the full episode",
    "Cutting the shorts",
    "Writing the text",
)


def new_job_id() -> str:
    """Short, unguessable, and safe inside a folder name."""
    return secrets.token_hex(6)


def job_dir(job_id: str) -> Path:
    return config.JOBS_DIR / job_id


def _state_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def create(job_id: str, source: str, source_kind: str) -> dict[str, Any]:
    """Register a new job and write its initial state to disk."""
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    (job_dir(job_id) / "outputs").mkdir(exist_ok=True)

    state = {
        "id": job_id,
        "source": source,
        "source_kind": source_kind,      # "link" or "upload"
        "status": "queued",              # queued | running | done | failed
        "stage": STAGES[0],
        "stage_index": 0,
        "stage_count": len(STAGES),
        "message": "Waiting to start",
        "error": None,
        "created_at": time.time(),
        "finished_at": None,
        "duration_seconds": None,
        "outputs": {"shorts": [], "episode": None, "text": []},
    }
    _write(state)
    return state


def _write(state: dict[str, Any]) -> None:
    """Write state atomically, so a poll never reads a half-written file."""
    path = _state_path(state["id"])
    temporary = path.with_suffix(".tmp")
    with _WRITE_LOCK:
        temporary.write_text(json.dumps(state, indent=1), encoding="utf-8")
        temporary.replace(path)


def read(job_id: str) -> dict[str, Any] | None:
    """Current state, or None if there is no such job."""
    path = _state_path(job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def update(job_id: str, **changes: Any) -> dict[str, Any] | None:
    """Merge changes into a job's state."""
    state = read(job_id)
    if state is None:
        return None
    state.update(changes)
    _write(state)
    return state


def set_stage(job_id: str, stage: str, message: str = "") -> None:
    """Advance the job to a named stage, for the browser's progress list."""
    try:
        index = STAGES.index(stage)
    except ValueError:
        index = 0
    update(
        job_id,
        status="running",
        stage=stage,
        stage_index=index,
        message=message or stage,
    )


def fail(job_id: str, error: str) -> None:
    """Record a failure in terms the person reading it can act on."""
    update(
        job_id,
        status="failed",
        error=error,
        message=error,
        finished_at=time.time(),
    )


def finish(job_id: str, outputs: dict[str, Any]) -> None:
    state = read(job_id) or {}
    started = state.get("created_at", time.time())
    update(
        job_id,
        status="done",
        stage="Finished",
        stage_index=len(STAGES),
        message="Finished",
        outputs=outputs,
        finished_at=time.time(),
        duration_seconds=round(time.time() - started, 1),
    )


def recent(limit: int = 25) -> list[dict[str, Any]]:
    """Jobs newest first, for the history list in the interface."""
    if not config.JOBS_DIR.is_dir():
        return []
    states = []
    for directory in config.JOBS_DIR.iterdir():
        if not directory.is_dir():
            continue
        state = read(directory.name)
        if state:
            states.append(state)
    states.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return states[:limit]
