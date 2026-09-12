# GRIOT OS

**Strategic Intelligence & Execution Agent for Thomas's project portfolio**

GRIOT OS is a personal strategic operating system that combines brand storytelling, market development, data science, software engineering and operations.

It is designed to become a **better, more systematic version of your professional skill set** — not a generic chatbot.

> **Think like a strategist. Validate like a data scientist. Build like a software engineer. Communicate like a storyteller. Operate like an owner.**
>
> **Never confuse activity with progress.**

## What GRIOT OS is for

GRIOT helps move work from:

**idea → evidence → strategy → decision → execution → measurement → learning**

It is intended to work across:

| Project | GRIOT role |
|---|---|
| **SpeakPower** | Brand storytelling, communications, positioning and market development |
| **Tonninyira** | Product strategy, marketplace analysis, software, growth and operations |
| **CuePointe** | Community growth, tournament operations, brand and partnership strategy |
| **UBF** | Conservation communications, AI/process automation and organizational operations |
| **FoB** | Biodiversity/community ecosystem, operations and strategic development |
| **Other ventures** | Business analysis, brand strategy, research and project operations |

## The strategic brain

Every important request should pass through:

1. **UNDERSTAND** — What exactly is happening?
2. **CONTEXT** — Which project, audience and objective matter?
3. **EVIDENCE** — What do we actually know?
4. **DIAGNOSE** — What is causing the problem?
5. **OPTIONS** — What realistic choices exist?
6. **RECOMMEND** — Which option is strongest and why?
7. **EXECUTE** — What can safely be done?
8. **MEASURE** — Which KPI tells us whether it worked?
9. **LEARN** — What should be remembered for next time?

GRIOT distinguishes **FACT, INFERENCE, HYPOTHESIS, RECOMMENDATION and UNKNOWN** so assumptions are not quietly presented as evidence.

## Specialist agents

- `StoryAgent` — storytelling, copy, narratives, campaigns
- `MarketAgent` — market research, competition, segmentation and opportunities
- `DataAgent` — SQL, Python, metrics, statistics and dashboards
- `DevAgent` — code, GitHub, APIs, architecture and debugging
- `ResearchAgent` — evidence gathering and web research
- `GrowthAgent` — acquisition, retention, partnerships and monetization
- `OperationsAgent` — workflows, SOPs and automation
- `BrandAgent` — brand consistency across channels and assets
- `StrategyAgent` — synthesizes the work and makes the final strategic recommendation

`StrategyAgent` is the chief thinker. The specialists provide depth.

## Where you actually use GRIOT

**The GitHub repository is the source code. It is not the app interface.**

The intended user flow is:

```text
You
  ↓
GRIOT Web App
  ↓
Strategic Orchestrator
  ↓
Memory + Specialist Agents
  ↓
Approved Tools / Project Systems
```

The current build includes a real browser interface in `griot-os/public/` plus the FastAPI backend.

### Local use

Run the backend locally and open:

```text
http://127.0.0.1:8000
```

### Production use

The recommended production deployment is **Vercel + Postgres (Neon through the Vercel Marketplace)**, with Cloudflare used for DNS/domain management if desired.

Vercel supports FastAPI directly on its Python runtime and can serve the static web interface through `public/`. Its Marketplace supports managed Postgres providers such as Neon. See `docs/GRIOT_OS_DEPLOYMENT.md` for the exact setup.

## When you should use GRIOT

Use GRIOT when a question requires **judgment, evidence, strategy or coordination across several skills**.

Good examples:

```text
Project: Tonninyira
Registrations are growing but orders are not. Diagnose the likely bottleneck.

Project: SpeakPower
Turn this idea into a campaign based on what the audience is feeling and what the market is saying.

Project: CuePointe
Compare these growth ideas and recommend the one with the strongest strategic upside.

Project: UBF
Analyze this workflow and identify where AI could reduce repetitive work without creating operational risk.

Portfolio
Look across my projects for reusable strategic patterns and conflicts in priorities.
```

For a tiny one-off task, a normal assistant or direct tool is usually faster. The question is:

> **Does this task need strategic judgment, project context, evidence, analysis or coordinated execution?**

## How to prompt GRIOT

### 1. Name the project

```text
Project: Tonninyira
```

### 2. State the problem, not only the task

Weak:

```text
Write a marketing post.
```

Better:

```text
Tonninyira vendors are signing up but many are not uploading their first products. Diagnose why and propose a retention campaign.
```

### 3. Force evidence discipline

Useful requests:

```text
Separate facts from assumptions.
What evidence would change your recommendation?
Challenge my idea.
What is the real bottleneck?
```

### 4. Choose the operating level

| Level | Use |
|---|---|
| **Observe** | Read and inspect information |
| **Analyze** | Diagnose and recommend |
| **Draft** | Prepare code, content, SQL, designs or plans |
| **Execute with approval** | Make external changes after your approval |
| **Controlled autonomy** | Run pre-approved, reversible workflows |

High-risk actions remain behind approval gates.

### 5. Finish with measurement

Ask:

```text
What should we measure after doing this?
```

## Memory

GRIOT supports local SQLite memory for development and **Postgres memory for production**.

Production memory is organized around:

- identity and professional principles
- project knowledge
- decisions and why they were made
- brand knowledge
- technical architecture
- market intelligence
- experiments and KPIs
- cross-project lessons

The application automatically uses Postgres when `DATABASE_URL` is configured and falls back to SQLite locally.

## Running locally

```bash
cd griot-os
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Configure:

```env
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your_model_here
DATABASE_URL=
```

Then:

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

## Production deployment

The production path is:

```text
GitHub
   ↓
Vercel
   ├── FastAPI backend
   └── GRIOT web interface
        ↓
Neon Postgres
        ↓
GRIOT memory / decisions / KPIs
        ↓
GitHub + project APIs + research + future tools
```

Cloudflare can sit in front as the DNS and domain layer. There is no requirement for Supabase in this architecture.

See:

**`docs/GRIOT_OS_DEPLOYMENT.md`**

for the deployment checklist and environment variables.

## Safety and approvals

The agent is deliberately designed to challenge assumptions and request approval before risky external actions. Do not give it destructive database permissions, unrestricted production credentials or financial authority.

## Repository status

The GRIOT OS implementation lives on the `griot-os-v1` branch while it is being reviewed. It includes the strategic brain, specialist routing, local/production memory support, browser interface, FastAPI API and deployment scaffolding.

The long-term goal is not an AI that simply answers Thomas's questions.

The goal is an AI that can **understand the portfolio, think strategically, work with evidence, build solutions, learn from outcomes and safely execute approved operations.**
