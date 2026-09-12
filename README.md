# GRIOT OS

**Strategic Intelligence & Execution Agent for Thomas's project portfolio**

GRIOT OS is the successor direction of this repository: a personal strategic operating system that combines brand storytelling, market development, data science, software engineering and operations.

It is designed to become a **better, more systematic version of your professional skill set** — not a generic chatbot.

> **Think like a strategist. Validate like a data scientist. Build like a software engineer. Communicate like a storyteller. Operate like an owner.**
>
> **Never confuse activity with progress.**

## What GRIOT OS is for

GRIOT OS helps you move from:

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

Every important request should pass through this decision protocol:

1. **UNDERSTAND** — What exactly is happening?
2. **CONTEXT** — Which project, audience and objective matter?
3. **EVIDENCE** — What do we actually know?
4. **DIAGNOSE** — What is causing the problem?
5. **OPTIONS** — What realistic choices exist?
6. **RECOMMEND** — Which option is strongest and why?
7. **EXECUTE** — What can safely be done?
8. **MEASURE** — Which KPI tells us whether it worked?
9. **LEARN** — What should be remembered for next time?

GRIOT also distinguishes **FACT, INFERENCE, HYPOTHESIS, RECOMMENDATION and UNKNOWN** so that assumptions are not quietly presented as evidence.

## Specialist agents

GRIOT routes work to specialist capabilities when needed:

- `StoryAgent` — storytelling, copy, narratives, campaigns
- `MarketAgent` — market research, competition, segmentation and opportunities
- `DataAgent` — SQL, Python, metrics, statistics and dashboards
- `DevAgent` — code, GitHub, Supabase, APIs, architecture and debugging
- `ResearchAgent` — evidence gathering and web research
- `GrowthAgent` — acquisition, retention, partnerships and monetization
- `OperationsAgent` — workflows, SOPs and automation
- `BrandAgent` — brand consistency across channels and assets
- `StrategyAgent` — synthesizes the work and makes the final strategic recommendation

`StrategyAgent` is the chief thinker. The specialists provide depth.

## Memory

The first version supports persistent local memory and decision logs. The target production architecture uses a dedicated Supabase/Postgres memory layer.

Memory is organized around:

- identity and professional principles
- project knowledge
- decisions and why they were made
- brand knowledge
- technical architecture
- market intelligence
- experiments and KPIs
- cross-project lessons

## When you should use GRIOT

Use GRIOT when a question requires **judgment, evidence, strategy or coordination across several skills**.

Good examples:

```text
"Tonninyira registrations are growing but orders are not. Diagnose the likely bottleneck."

"Turn this SpeakPower idea into a campaign based on what the audience is feeling and what the market is saying."

"Review this GitHub change from a product, engineering and business perspective before I merge it."

"Compare these three CuePointe growth ideas and recommend the one with the strongest strategic upside."

"Analyze the UBF workflow and identify where AI could reduce repetitive work without creating operational risk."
```

## When NOT to use GRIOT

Do not use it merely to generate busywork that has no clear outcome.

For a simple one-off task — such as fixing a typo or writing a two-line message — a normal assistant or direct tool is usually faster.

The question to ask is:

> **Does this task need strategic judgment, project context, evidence, analysis or coordinated execution?**

If the answer is yes, GRIOT is probably the right tool.

## How to use it

### 1. Tell it the project

Always name the project when the context matters:

```text
Project: Tonninyira
```

### 2. State the problem, not only the task

Weak:

```text
"Write a marketing post."
```

Better:

```text
"Tonninyira vendors are signing up but many are not uploading their first products. Diagnose why and propose a retention campaign."
```

### 3. Ask it to show its evidence and assumptions

Useful prompts:

```text
"Separate facts from assumptions."
"What evidence would change your recommendation?"
"Challenge my idea."
"What is the real bottleneck?"
```

### 4. Decide the operating level

GRIOT is designed around increasing autonomy:

| Level | Use |
|---|---|
| **Observe** | Read and inspect information |
| **Analyze** | Diagnose and recommend |
| **Draft** | Prepare code, content, SQL, designs or plans |
| **Execute with approval** | Make external changes after your approval |
| **Controlled autonomy** | Run pre-approved, reversible workflows |

Keep high-risk actions under human approval, especially money movement, destructive database operations, production deployments, contracts and public statements.

### 5. End with a measurement question

Ask:

```text
"What should we measure after doing this?"
```

That prevents the agent from turning activity into false progress.

## Useful operating commands

The intended interface supports commands such as:

- `/think` — deep strategic analysis
- `/research` — gather evidence
- `/analyze` — inspect data and metrics
- `/build` — plan or implement software changes
- `/campaign` — develop a brand/market campaign
- `/audit` — find weaknesses and risks
- `/measure` — review KPIs and outcomes
- `/decide` — compare options and recommend one
- `/learn` — store validated lessons
- `/portfolio` — look for useful patterns across projects

## Example workflow

```text
YOU:
Project: SpeakPower
Analyze the last 30 days of performance. Identify the strongest audience signal,
compare it with current market conversations, and propose the next campaign.

GRIOT:
1. Retrieves project memory and available performance data.
2. Separates facts, inferences and unknowns.
3. Researches relevant market signals.
4. Diagnoses the strongest opportunity.
5. Recommends a campaign and explains why.
6. Defines KPIs.
7. Prepares implementation assets.
8. Requests approval before publishing or changing external systems.
9. Stores the decision and later outcome.
```

## Running the current prototype

The v0.1 backend is a FastAPI service.

### Requirements

- Python 3.11+
- an OpenAI-compatible API key for full model reasoning

### Setup

```bash
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Set the model credentials in `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your_model_here
```

Then run:

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

The service exposes project routing, agent routing, chat, memory and approval endpoints.

## Production direction

The prototype deliberately keeps production mutations disabled. The intended production setup is:

```text
GRIOT OS
   |
   +-- Strategy / Orchestrator
   |
   +-- Specialist Agents
   |
   +-- Dedicated Supabase/Postgres Memory
   |
   +-- GitHub
   +-- Tonninyira Supabase
   +-- UBF/FoB systems
   +-- Canva
   +-- Web research
   +-- Analytics
   +-- Automation
```

Each external system should be connected through explicit, least-privilege tools and approval gates.

## Repository status

This branch contains the GRIOT OS v0.1 bootstrap. It is intentionally isolated from `main` until reviewed.

The long-term goal is not to create an AI that simply answers Thomas's questions.

The goal is to create an AI that can **understand the portfolio, think strategically, work with evidence, build solutions, learn from outcomes and safely execute approved operations.**
