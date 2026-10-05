# GRIOT OS — Deployment Guide

## Recommended production stack

Use:

- **GitHub** — source code
- **Vercel** — web app + FastAPI API
- **Neon Postgres** — durable GRIOT memory
- **Cloudflare** — optional DNS/custom-domain layer
- **Claude API** — model reasoning

Supabase is not required for GRIOT's production memory. Vercel currently supports FastAPI on its Python runtime, and Neon is available as a Vercel Marketplace Postgres integration with plans starting at $0.

## 1. Import the repository into Vercel

Create a new Vercel project from:

`https://github.com/SpeakPower-commits/claude-central-agent`

Set the **Root Directory** to:

`griot-os`

Do not deploy the repository root. The GRIOT application lives inside the `griot-os` directory.

Vercel runs the FastAPI app through `api/index.py`. `vercel.json` rewrites every path to
that entrypoint, and FastAPI serves the browser interface from `app/static/`.

Do not add a `public/` directory. Vercel serves static files before applying rewrites, so a
`public/index.html` would shadow the application at `/` and you would see a stale page while
the API still answered on other paths.

## 2. Add the production database

In the Vercel project, open **Storage / Marketplace** and add **Neon Postgres**.

The Neon integration can provision a managed Postgres database and exposes `DATABASE_URL` to the project. Neon has a free plan and can scale later.

## 3. Add the Claude environment variables

In Vercel Project Settings → Environment Variables, add:

```env
ANTHROPIC_API_KEY=your_api_key
ANTHROPIC_MODEL=claude-opus-5
GRIOT_API_KEY=generate_a_long_random_string
DATABASE_URL=provided_by_neon
```

Generate `GRIOT_API_KEY` with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set all four for the **Production** environment, and delete any leftover
`OPENAI_*` variables. The application refuses to start on Vercel without
`DATABASE_URL` and `GRIOT_API_KEY`, so a missing one fails the deploy loudly
instead of silently serving a degraded app.

Never put the Claude API key in browser JavaScript or a Git-tracked `.env` file.

## 4. Deploy to production

Pushes to the selected branch trigger deployments automatically once the GitHub
repository is connected to Vercel.

A branch push produces a **preview** deployment. Previews do not serve your
production domain -- a project whose deployments are all previews shows
`"live": false` and nothing answers on `claude-central-agent.vercel.app`.
Promote a build to production from the deployment's **⋯ → Promote to
Production**, or merge the branch into the project's production branch.

For local verification, Vercel's FastAPI tooling can also run the project locally.

## 5. Turn off Vercel Authentication

New projects enable **Vercel Authentication**, which puts an SSO wall in front
of every `.vercel.app` URL. While it is on, only signed-in members of your
Vercel account can reach the app -- not your phone, and not anyone you share
the link with.

Settings → Deployment Protection → **Vercel Authentication → Disabled**.

This is safe only because the application now enforces its own `GRIOT_API_KEY`
on every route that reads or spends. Do not disable it before that key is set.

## 6. Verify the production app

```bash
curl -s https://<your-deployment>/health | jq
```

Expect `status: ok`, `memory: "postgres"`, `database_ready: true`,
`model_ready: true` and `auth_enabled: true`. Then:

```bash
curl -s -X POST https://<your-deployment>/chat \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $GRIOT_API_KEY" \
  -d '{"message":"Audit the current product strategy.","project":"tonninyira"}' | jq
```

Then send a test request from the GRIOT interface:

```text
Project: Tonninyira
Audit the current product strategy. Separate facts from assumptions and tell me what we should measure next.
```

The response should show the routed specialist agents and the memory count.

## 7. Add a custom domain

A clean production setup is:

```text
griot.yourdomain.com
        ↓
      Vercel
        ↓
  GRIOT Web App
```

Cloudflare can remain your DNS provider. Point the custom subdomain to the Vercel deployment using the DNS records Vercel gives you.

## 8. Production checklist

Before calling GRIOT production-ready:

- [ ] A deployment is promoted to **production** (`"live": true`)
- [ ] Vercel Authentication is disabled, and `GRIOT_API_KEY` is set
- [ ] `/health` returns `status: ok` with `auth_enabled: true`
- [ ] `/health` reports `memory: "postgres"`, not `sqlite`
- [ ] A request without `X-API-Key` returns 401
- [ ] Claude API key works server-side (`model_ready: true`)
- [ ] All `OPENAI_*` variables are deleted
- [ ] Memory and threads survive a redeploy
- [ ] Neon's **pooled** connection string is in use
- [ ] No `.env` or API credentials are committed
- [ ] External write actions remain approval-gated

## 9. Why this stack

The practical goal is to avoid making GRIOT dependent on one vendor for every layer.

Vercel handles the application runtime and deployment. Neon handles Postgres memory. Cloudflare can handle DNS. Anthropic supplies the reasoning model (Claude). GitHub remains the source of truth.

That gives GRIOT a clean path from a local prototype to a real hosted application without putting the agent's memory inside any of your existing business databases.
