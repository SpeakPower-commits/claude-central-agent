# GRIOT OS — Deployment Guide

## Recommended production stack

Use:

- **GitHub** — source code
- **Vercel** — web app + FastAPI API
- **Neon Postgres** — durable GRIOT memory
- **Cloudflare** — optional DNS/custom-domain layer
- **OpenAI API** — model reasoning

Supabase is not required for GRIOT's production memory. Vercel currently supports FastAPI on its Python runtime, and Neon is available as a Vercel Marketplace Postgres integration with plans starting at $0. citeturn303451search1turn303451search0

## 1. Import the repository into Vercel

Create a new Vercel project from:

`https://github.com/SpeakPower-commits/claude-central-agent`

Set the **Root Directory** to:

`griot-os`

Do not deploy the repository root. The GRIOT application lives inside the `griot-os` directory.

Vercel detects the Python FastAPI entrypoint under `api/index.py` and the browser interface under `public/`.

## 2. Add the production database

In the Vercel project, open **Storage / Marketplace** and add **Neon Postgres**.

The Neon integration can provision a managed Postgres database and exposes `DATABASE_URL` to the project. Neon has a free plan and can scale later. citeturn303451search0turn303451search3

## 3. Add the OpenAI environment variables

In Vercel Project Settings → Environment Variables, add:

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.6-luna
DATABASE_URL=provided_by_neon
```

Never put the OpenAI key in `public/`, browser JavaScript or a Git-tracked `.env` file.

## 4. Deploy

Pushes to the selected branch can trigger deployments automatically once the GitHub repository is connected to Vercel.

For local verification, Vercel's FastAPI tooling can also run the project locally. citeturn303451search1turn303451search8

## 5. Verify the production app

Check:

```text
/
/api/docs
/api/health
```

Then send a test request from the GRIOT interface:

```text
Project: Tonninyira
Audit the current product strategy. Separate facts from assumptions and tell me what we should measure next.
```

The response should show the routed specialist agents and the memory count.

## 6. Add a custom domain

A clean production setup is:

```text
griot.yourdomain.com
        ↓
      Vercel
        ↓
  GRIOT Web App
```

Cloudflare can remain your DNS provider. Point the custom subdomain to the Vercel deployment using the DNS records Vercel gives you.

## 7. Production checklist

Before calling GRIOT production-ready:

- [ ] Vercel deployment succeeds
- [ ] `/api/health` returns `status: ok`
- [ ] OpenAI key works server-side
- [ ] Neon connection works
- [ ] Memory survives a redeploy
- [ ] Decisions are written to Postgres
- [ ] Browser can chat with `/api/chat`
- [ ] API docs are not accidentally exposing secrets
- [ ] No `.env` or API credentials are committed
- [ ] Production tool permissions remain least-privilege
- [ ] External write actions remain approval-gated

## 8. Why this stack

The practical goal is to avoid making GRIOT dependent on one vendor for every layer.

Vercel handles the application runtime and deployment. Neon handles Postgres memory. Cloudflare can handle DNS. OpenAI supplies the reasoning model. GitHub remains the source of truth.

That gives GRIOT a clean path from a local prototype to a real hosted application without putting the agent's memory inside any of your existing business databases.
