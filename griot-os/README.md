# GRIOT OS

Strategic Intelligence & Execution Agent for SpeakPower, Tonninyira, CuePointe, UBF/FoB and future projects.

## Included in v0.1

- Shared strategic brain and decision protocol
- Project-specific context
- Specialized agent routing
- Evidence discipline: fact / inference / hypothesis / recommendation / unknown
- Persistent local memory and decision logs
- Per-tenant isolation (`X-Tenant-Id`) so one deployment can serve several clients
- A client workspace, every route scoped to the caller's tenant:
  - `POST /chat` takes optional `lenses` (up to 3 keys from `/agents`) in place of automatic routing, and optional `effort` (`low` / `medium` / `high`) and `max_output_tokens` (1,000-16,000, never above `GRIOT_MAX_OUTPUT_TOKENS`) so a front end can bound the cost of a client's turn. An answer that reaches the limit says so.
  - `GET /threads` lists conversations with their first question; `GET /decisions` lists the decision log; `DELETE /memories/{id}` removes one memory.
  - Memories of kind `profile` (what a client states about themselves: role, goal, why now) are pinned: every chat turn sees them first, however many newer memories exist. `GET /memories?limit=` lists up to 200.
  - `/health` reports `"workspace": true` once these exist.
- Approval endpoint for future execution actions
- OpenAI-compatible model adapter
- FastAPI backend with Swagger docs

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs

## Architecture direction

SQLite is the local fallback. Production memory should use Supabase/Postgres, with repositories, analytics, web research and brand tools connected through explicit, least-privilege execution tools and approval gates.
