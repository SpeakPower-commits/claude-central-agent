# GRIOT OS Launch Guide

## What you use

The normal GRIOT experience is the web app served by the FastAPI backend. You do not need to work from raw API endpoints for normal use.

## Run it locally

1. Install Python 3.12+.
2. Open a terminal in `griot-os/`.
3. Create and activate a virtual environment.
4. Install dependencies: `pip install -r requirements.txt`.
5. Copy `.env.example` to `.env`.
6. Add your model API key to `.env`.
7. Start: `uvicorn app.main:app --reload`.
8. Open `http://127.0.0.1:8000`.
9. Use `/docs` only when you need to inspect or test the API directly.

## First conversation

Select a project and ask a problem-oriented question.

Good:

> Audit Tonninyira. Identify the top three growth constraints from the evidence we have, challenge my assumptions, and tell me what I should do next.

Weak:

> Give me some Tonninyira ideas.

The first gives GRIOT a decision to work on. The second asks for generic activity.

## Project selection

- SpeakPower: positioning, audience, storytelling, campaigns, offers and market development.
- Tonninyira: product decisions, marketplace growth, engineering trade-offs, data analysis and operations.
- CuePointe: events, community growth, sponsorships, tournament operations and brand development.
- UBF: conservation communications, stakeholder strategy, process improvement and AI automation.
- FoB: biodiversity/community strategy, platform operations and ecosystem growth.
- Portfolio / Other: cross-project priorities and decisions.

## How to prompt GRIOT

Use this pattern when possible:

**Situation → Objective → Evidence → Constraint → Decision needed**

Example:

> Situation: Tonninyira has traffic but repeat purchases appear weak.
> Objective: increase repeat purchase frequency.
> Evidence: I have orders and customer data.
> Constraint: small engineering capacity.
> Decision: diagnose the bottleneck and recommend the highest-impact intervention.

## Modes of work

### THINK
Use for strategic analysis, diagnosis and challenge.

### RESEARCH
Use when external evidence or current market information is needed.

### ANALYZE
Use for SQL, Python, KPIs, experiments and data diagnosis.

### BUILD
Use when the result should become software, an automation or a technical change.

### CAMPAIGN
Use for audience strategy, messaging, content systems and brand storytelling.

### AUDIT
Use to find weaknesses, risk, wasted effort or missing evidence.

### MEASURE
Use to evaluate whether a strategy or experiment actually worked.

## When GRIOT should challenge you

Expect GRIOT to say that an idea is weak when the evidence is weak. That is a feature, not a failure.

It should distinguish:

- FACT — directly supported.
- INFERENCE — reasonable interpretation.
- HYPOTHESIS — needs testing.
- RECOMMENDATION — proposed action.
- UNKNOWN — missing information.

## Approval rule

Do not give GRIOT production credentials just so it can act freely.

The intended progression is:

1. Observe.
2. Analyze.
3. Draft.
4. Execute with approval.
5. Controlled autonomy for low-risk, reversible workflows.

Financial actions, destructive database changes, production deployments and public commitments should require human approval.

## Daily use

Start the day with:

> Review my projects and identify the one decision that most needs my attention today. Explain why.

During work:

> Challenge this plan before I implement it.

End of day:

> Record today's important decisions, assumptions and lessons that should become project memory.

Weekly:

> Review project performance, compare outcomes with our intended KPIs, and tell me what we should stop, start and continue.

## Important current limitation

The production GRIOT memory database is not yet connected. The current app uses local SQLite memory as a development fallback.

A separate Supabase project is preferred for production memory. The current Supabase organization has reached its two-active-free-project limit, so do not repurpose Tonninyira or FoB merely to make room for GRIOT.

## Security

Never commit `.env`, API keys, service-role keys, access tokens or other secrets to this public repository. Keep secrets in environment variables managed by the eventual hosting provider.
