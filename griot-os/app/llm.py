"""Claude integration: prompt construction, the reasoning call, and memory distillation."""

from __future__ import annotations

import json
import logging

import anthropic
from fastapi import HTTPException

from . import config
from .domain import AGENTS, PROJECTS, STEPS

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

ORCHESTRATION_ONLY_NOTICE = (
    "GRIOT OS is running in orchestration-only mode. Set ANTHROPIC_API_KEY to enable "
    "model reasoning. Project routing, memory, decision logging and the interface are active."
)

MEMORY_SYSTEM_PROMPT = """You distil a strategic exchange into one durable memory for a project knowledge base.

Return ONLY a JSON object, no prose and no code fence:
{"title": "<= 10 words", "content": "1-2 sentences worth remembering later",
 "kind": "decision|insight|constraint|metric|context",
 "confidence": "fact|inference|hypothesis|recommendation|unknown"}

Record only what stays true beyond this exchange: a decision taken, a constraint
discovered, a durable fact about the business. If the exchange contains nothing
worth remembering, return {"skip": true}."""


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def route(text: str) -> list[str]:
    """Select specialist labels from the request.

    Matching is on word boundaries: substring matching previously routed
    "how do I make our customers happy" to DevAgent, because "app" occurs
    inside "happy".
    """
    import re

    words = set(re.findall(r"[a-z]+", text.lower()))

    rules: list[tuple[set[str], list[str]]] = [
        ({"brand", "story", "storytelling", "copy", "campaign", "content", "audience",
          "message", "messaging", "narrative"}, ["story", "brand"]),
        ({"market", "customer", "customers", "competitor", "competitors", "growth",
          "sales", "revenue", "pricing", "demand"}, ["market", "growth"]),
        ({"data", "kpi", "kpis", "metric", "metrics", "sql", "python", "analysis",
          "statistics", "forecast", "cohort"}, ["data"]),
        ({"code", "github", "bug", "api", "software", "deploy", "deployment",
          "database", "architecture", "latency"}, ["dev"]),
        ({"research", "evidence", "trend", "trends", "benchmark", "study"}, ["research"]),
        ({"process", "workflow", "sop", "automation", "operations", "ops",
          "logistics", "staffing"}, ["operations"]),
    ]

    agents: list[str] = []
    for triggers, selected in rules:
        if words & triggers:
            agents += selected

    if not agents:
        agents = ["strategy"]
    if "strategy" not in agents:
        agents.append("strategy")
    return list(dict.fromkeys(agents))


# How the person asked GRIOT to answer, chosen with a button rather than
# written into the question. Each replaces the default structure for one turn;
# the evidence labels still apply.
ANSWER_MODES = {
    "challenge": (
        "CHALLENGE. Pressure-test the idea instead of supporting it. Use this structure instead of the one above:\n"
        "1. The idea at its strongest, in two sentences\n"
        "2. The five weakest assumptions, ranked by how much damage each would do if wrong, each with a quick way to test it\n"
        "3. The toughest objection a donor, investor or board would raise, and how to answer it\n"
        "4. What would change your verdict\n"
        "5. Verdict: proceed, rework or stop, and why"
    ),
    "diagnose": (
        "DIAGNOSE. Find the root cause before suggesting any fix. Use this structure instead of the one above:\n"
        "1. Symptoms: what is observed, kept apart from causes\n"
        "2. Three likely root causes, ranked, each with the evidence for it, the evidence against it, "
        "and the data that would confirm or rule it out\n"
        "3. The cause to address first, and why\n"
        "4. What not to fix yet\n"
        "5. The quickest test to confirm the diagnosis this week"
    ),
    "plan": (
        "PLAN. Turn the goal into an executable plan. Use this structure instead of the one above:\n"
        "1. The goal as a measurable outcome with a deadline (use the client's own deadline when known)\n"
        "2. Phases up to the deadline; in each, the actions, who owns them, by when, the resources needed and one KPI\n"
        "3. The main risks, each with how to reduce it\n"
        "4. What success looks like at the halfway point\n"
        "5. The first step to take this week"
    ),
}


def build_system_prompt(
    project: str | None,
    memories: list[dict],
    agents: list[str],
    documents: list[dict] | None = None,
    answer_mode: str | None = None,
    project_label: str | None = None,
) -> str:
    """Operator instruction: identity, protocol and retrieved memory.

    Deliberately separate from the user's request, which travels as a user turn.
    `project_label` is the name a client gave one of their own projects; it is
    shown in place of the slug, quoted as the client's own words.
    """
    project_context = PROJECTS.get(project or "other", "Cross-project strategic work")
    project_line = project or "cross-project"
    if project_label:
        project_line = f'"{project_label}" (the client\'s own project)'
        project_context = "A project the client set up and named themselves."
    memory_text = "\n".join(
        f"- [{item['confidence']}] {item['title']}: {item['content']}" for item in memories
    ) or "- No stored memories retrieved."
    documents_text = ""
    if documents:
        documents_text = (
            "\n\nCLIENT DOCUMENTS (excerpts from documents the client shared, chosen for this question). "
            "Each is a FACT about what that document says, not proof about the world. "
            "When you rely on one, cite its source in square brackets, e.g. [Annual report 2025, p. 4]:\n"
            + "\n".join(f"- [{item['source']}] {item['text']}" for item in documents)
        )

    mode_text = ""
    if answer_mode in ANSWER_MODES:
        mode_text = "\n\nANSWER MODE: " + ANSWER_MODES[answer_mode]

    return f"""You are GRIOT OS, Thomas's strategic intelligence and execution agent.

MISSION: Think like a strategist. Validate like a data scientist. Build like a software engineer. Communicate like a storyteller. Operate like an owner.

PROJECT: {project_line}
CONTEXT: {project_context}
ACTIVE AGENTS: {', '.join(AGENTS[key] for key in agents)}
DECISION PROTOCOL: {' → '.join(STEPS)}

EVIDENCE DISCIPLINE: label claims FACT, INFERENCE, HYPOTHESIS, RECOMMENDATION or UNKNOWN.
Never present an inference or hypothesis as a fact. Challenge weak assumptions.
Say plainly when you do not know. Never confuse activity with progress.

STORED MEMORY:
{memory_text}{documents_text}

Structure every substantive response as:
1. Diagnosis
2. Evidence and unknowns
3. Recommendation
4. Next actions
5. Measurement
6. Approval requirement

For a short clarifying exchange, answer directly instead of forcing the structure.{mode_text}"""


def _raise_for(exc: Exception) -> None:
    """Map SDK exceptions to HTTP responses, most specific first."""
    if isinstance(exc, anthropic.AuthenticationError):
        raise HTTPException(502, "ANTHROPIC_API_KEY is invalid or revoked")
    if isinstance(exc, anthropic.PermissionDeniedError):
        raise HTTPException(502, "Claude API key lacks permission for this model")
    if isinstance(exc, anthropic.NotFoundError):
        raise HTTPException(502, f"Unknown Claude model: {config.ANTHROPIC_MODEL}")
    if isinstance(exc, anthropic.RateLimitError):
        retry_after = exc.response.headers.get("retry-after", "60")
        raise HTTPException(429, f"Rate limited by the Claude API. Retry after {retry_after}s.")
    if isinstance(exc, anthropic.APIStatusError):
        code = 502 if exc.status_code >= 500 else exc.status_code
        raise HTTPException(code, exc.message)
    if isinstance(exc, anthropic.APIConnectionError):
        raise HTTPException(503, "Could not reach the Claude API")
    raise exc


def _text_of(response) -> str:
    return "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()


CUT_SHORT_NOTE = "\n\n_(This answer reached its length limit. Ask GRIOT to continue.)_"


async def analyse(
    system_prompt: str, history: list[dict], user_message: str,
    effort: str | None = None, max_tokens: int | None = None,
) -> str:
    """Run one strategic-analysis turn, with prior turns replayed for context.

    `effort` and `max_tokens` let a front end serving paying clients bound the
    cost of a turn. Effort is the lever that shortens reasoning; `max_tokens`
    is only a backstop and can never exceed GRIOT's own configured ceiling.
    """
    if not config.model_ready():
        return ORCHESTRATION_ONLY_NOTICE

    messages = [
        {"role": row["role"], "content": row["content"]}
        for row in history
        if row["role"] in ("user", "assistant") and row["content"]
    ]
    messages.append({"role": "user", "content": user_message})

    ceiling = min(max_tokens, config.MAX_OUTPUT_TOKENS) if max_tokens else config.MAX_OUTPUT_TOKENS
    # Sent as a raw body field so it works whatever the installed SDK types.
    extra = {"extra_body": {"output_config": {"effort": effort}}} if effort else {}

    try:
        response = await client().messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=ceiling,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
            **extra,
        )
    except Exception as exc:  # narrowed immediately by _raise_for
        _raise_for(exc)

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        raise HTTPException(422, f"Claude declined this request (category: {category})")

    answer = _text_of(response)
    if not answer:
        raise HTTPException(502, "Claude returned no text content")
    if response.stop_reason == "max_tokens":
        # Say so rather than pass off a cut-off answer as complete.
        answer += CUT_SHORT_NOTE
    return answer


async def distil_memory(
    project: str, user_message: str, answer: str
) -> dict | None:
    """Summarise an exchange into a memory row, or None if nothing is worth keeping.

    Runs on the cheap model: this is extraction, not reasoning. Failures are
    swallowed -- losing a memory must never fail the user's request.
    """
    if not config.model_ready():
        return None

    try:
        response = await client().messages.create(
            model=config.MEMORY_MODEL,
            max_tokens=512,
            system=MEMORY_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"PROJECT: {project}\n\n"
                        f"REQUEST:\n{user_message[:2000]}\n\n"
                        f"RESPONSE:\n{answer[:4000]}"
                    ),
                }
            ],
        )
        payload = json.loads(_text_of(response))
    except Exception:
        logger.warning("memory distillation failed", exc_info=True)
        return None

    if not isinstance(payload, dict) or payload.get("skip"):
        return None
    if not payload.get("title") or not payload.get("content"):
        return None

    valid_confidence = {"fact", "inference", "hypothesis", "recommendation", "unknown"}
    confidence = str(payload.get("confidence", "inference")).lower()

    return {
        "title": str(payload["title"])[:200],
        "content": str(payload["content"])[:2000],
        "kind": str(payload.get("kind", "insight"))[:40],
        "confidence": confidence if confidence in valid_confidence else "inference",
    }
