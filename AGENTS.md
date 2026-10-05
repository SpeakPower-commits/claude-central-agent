# AGENTS.md

Operating instructions for AI coding agents working in this repository.
Human contributors should read this too — it documents real traps.

---

## 1. What this repository is

Two independent systems share this repo. Know which one you are touching.

| Path | System | Runtime |
|---|---|---|
| `griot-os/` | **GRIOT OS** — strategic intelligence agent. FastAPI backend, vanilla-JS UI, SQLite/Postgres memory. | Python 3.11+ |
| `agent.js`, `.github/workflows/` | **Central Coding Agent** — CI job that writes files into *other* repositories via the GitHub API. | Node 20 |

They share no code. A change to one is almost never a change to the other.

**Active branch: `griot-os-v1`.** All work commits here. Never push to `main` without explicit instruction.

---

## 2. Ground truth over documentation

**The README and docs in this repo describe features that do not exist.** Do not treat them as a specification of current behaviour. Verify against code before relying on any claim.

Currently documented but **not implemented** — do not assume these work:

- **Approval gates.** `POST /approval` returns `404` unconditionally. Nothing inserts into the `actions` table.
- **Nine specialist agents.** There is one LLM call. `route()` selects label strings that get interpolated into a prompt.
- **Memory / learning.** Nothing writes memories automatically. `memory_used` is `0` unless a human `POST`s to `/memory`.
- **Operating modes.** `mode` is accepted by the request schema and ignored.
- **Tools / research / execution.** There are none. No web search, no SQL execution, no GitHub access from GRIOT.
- **Conversation history.** `/chat` is stateless. The UI renders a thread the backend never receives.

If you implement one of these, update the docs in the same change. If you cannot implement it, do not leave the doc claiming it.

---

## 3. GRIOT OS — setup and run

```bash
cd griot-os
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in OPENAI_API_KEY
python3 -m uvicorn app.main:app --reload
```

Serves on `http://127.0.0.1:8000`. UI at `/`, OpenAPI at `/docs`, health at `/health`.

Without `OPENAI_API_KEY` the app still starts and routes — `model()` returns an "orchestration-only mode" string. Useful for testing routing and persistence without spending tokens.

### Verify a change

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"diagnose growth","project":"tonninyira"}'
```

`/health` must return `status: ok`. `/chat` must return a `decision_id` and an `agents` array.

---

## 4. Known traps

Do not be surprised by these. Do not "discover" them as new bugs — fix them deliberately or leave them.

| Trap | Detail |
|---|---|
| **No `.gitignore`** | `.env`, `griot.db`, `.venv/`, `__pycache__/` are all untracked-but-committable. **Never run `git add .`** in this repo until a `.gitignore` exists. |
| **No authentication** | Every endpoint is open. Do not deploy publicly without adding auth first. |
| **`griot-os/public/` does not exist** | Docs reference it. The UI is at `griot-os/app/static/`. |
| **Vercel path is broken** | `vercel.json` has no rewrites; `api/index.py` will `ImportError` (no `sys.path` setup). Assume the deploy does not work until proven otherwise. |
| **Dockerfile build fails** | `COPY agent_manifest.json ./` — the file is at `app/agent_manifest.json`. |
| **SQLite on serverless** | Default `GRIOT_DB_PATH` writes to a read-only FS on Vercel. Production requires `DATABASE_URL`. |
| **Dead code** | `griot-os/supabase/migrations/` and `app/agent_manifest.json` have **zero references**. The migration's schema actively contradicts `SCHEMA_SQL` in `main.py`. Don't "align" to the migration — it is not the source of truth. |
| **`insert_row()` is order-dependent** | It zips `dict` insertion order against a hardcoded column string. Reordering a dict literal silently corrupts rows. |
| **`route()` is substring matching** | `"app"` matches `"happy"`. `"How do I make our customers happy?"` routes to DevAgent. Use word boundaries if you touch it. |
| **No connection pooling** | `psycopg.connect()` is called per request at four sites. Neon requires the *pooled* connection string. |

---

## 5. Model identifiers

Every model ID currently committed is invalid and will `404` at the provider. If you touch a call site, use a real one.

- **Anthropic:** `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`
- **Do not use:** `claude-sonnet-4-6` (`agent.js:77`, `claude-issue-agent.yml:81`) — not a real model.
- **Do not use:** `gpt-5.6-luna` (`.env.example`, `main.py:256`, deployment doc) — not a real model.

Never hardcode a model ID where an env var will do.

---

## 6. Security rules — non-negotiable

These exist because the repo currently violates all of them.

1. **Never commit credentials.** No `.env`, no keys in workflow files, no tokens in code. Secrets come from env vars or GitHub Secrets only.
2. **Never widen a CI trigger to untrusted input.** `claude-issue-agent.yml` currently fires on any issue containing `@claude`, from anyone, and feeds the issue body into a prompt while holding a cross-repo PAT. That is prompt injection into a write token. Gate on `author_association == 'OWNER'` or `workflow_dispatch` only.
3. **Never write to a default branch from an agent.** `agent.js` currently `PUT`s model output straight to `main` via the Contents API. Any change here must create a branch and open a PR. A human reviews the diff.
4. **Never `PUT` unvalidated model output to a file.** Validate it parses/compiles before committing.
5. **Least privilege on tokens.** `REPOS_PAT` should be scoped to the specific repos it needs, nothing more.

If a task asks you to bypass one of these, stop and raise it rather than complying.

---

## 7. Code standards

Inherited from `CLAUDE.md`, which remains authoritative on tone and persona.

- **Python:** type hints on function signatures, `from __future__ import annotations` at the top (matches existing style in `main.py`). Explicit error handling — no bare `except`. Descriptive names.
- **JavaScript:** no build step, no framework. Plain ES modules and DOM APIs, matching `app/static/app.js`.
- **Match the surrounding file.** This codebase uses lowercase SQL keywords, 4-space Python indent, 2-space JS indent. Follow what is there.
- **Do not remove analytics or conversion hooks** if any are added later.
- **Error handling is not optional.** Every external call (model API, database, GitHub) needs an explicit failure path.

### Commits

Conventional-commit prefixes, matching existing history: `feat:`, `fix:`, `docs:`, `chore:`, `deploy:`, `style:`.
Scope where useful: `feat(griot): ...`

---

## 8. Testing

**There are currently no tests and no CI for the Python app.** If you add meaningful logic, add a test with it.

Target layout when tests are introduced:

```
griot-os/tests/test_api.py      # /health, /chat, /memory round-trip
griot-os/tests/test_routing.py  # route() edge cases
```

Until a runner is configured, verify by hand with the `curl` commands in §3 and say so explicitly in your summary. **Never report a change as verified if you only read the code.**

---

## 9. Reporting

When you finish a task, state plainly:

- What you changed, by file.
- What you actually ran to verify it, and the result.
- What you did **not** do, and why.

Do not describe unimplemented work as complete. The gap between this repo's documentation and its behaviour is its single biggest liability — do not widen it.
