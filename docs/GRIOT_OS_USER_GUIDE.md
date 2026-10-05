# GRIOT OS User Guide

## Why use GRIOT?

The common mistake with AI agents is to use them as faster search boxes. GRIOT is meant for something different: **strategic work that needs context, judgment, evidence and coordinated execution**.

Use it when the question is not simply "What should I write?" but rather:

> **What is really happening, why is it happening, what should we do, and how will we know it worked?**

---

## 1. WHERE should I use GRIOT?

Use the GRIOT interface/API when the work involves one or more of these:

| Situation | Use GRIOT? | Why |
|---|---:|---|
| Strategic decision | **Yes** | It can compare options and challenge assumptions |
| Market opportunity | **Yes** | Combines market, audience and evidence thinking |
| Brand positioning | **Yes** | Brings storytelling and market development together |
| Product/growth problem | **Yes** | Can move from diagnosis to data and execution |
| Software architecture decision | **Yes** | Brings product + technical + business context |
| KPI/performance review | **Yes** | Designed around evidence and measurement |
| Cross-project opportunity | **Yes** | Can compare lessons across the portfolio |
| Routine one-line rewrite | Usually no | A normal assistant is faster |
| Simple typo fix | No | No strategic reasoning is needed |
| Pure brainstorming with no decision needed | Usually no | GRIOT is strongest when ideas must become decisions |

### Where physically?

For v0.1, GRIOT runs as a backend service with API documentation at `/docs`.

The intended production experience is a simple web dashboard/chat interface connected to its own strategic memory layer.

---

## 2. WHAT should I give GRIOT?

Give it four things whenever possible:

### A. Project

Name the project:

```text
Project: Tonninyira
```

### B. Objective

Say what you are trying to achieve:

```text
Objective: Increase repeat purchases.
```

### C. Problem or opportunity

Describe what you are seeing:

```text
Orders are growing, but most customers are buying only once.
```

### D. Constraints

Mention the limits:

```text
Budget is small.
We cannot redesign the entire app this month.
```

Then ask GRIOT to investigate rather than jumping straight to a solution.

---

## 3. HOW should I ask it?

### Weak prompt

```text
Write a Tonninyira marketing campaign.
```

### Stronger prompt

```text
Project: Tonninyira

Problem: New customers are registering, but repeat purchase is weak.

Goal: Improve repeat purchase without increasing paid advertising spend.

Investigate the likely causes, separate facts from assumptions,
propose 3 options, recommend the strongest one, and define the KPI
we should watch.
```

The second prompt gives GRIOT something it can reason about.

---

## 4. WHICH GRIOT capability should I call?

You normally do not need to choose an internal agent manually. GRIOT should route the work.

However, you can think in these terms:

| Need | Main capability |
|---|---|
| Story, copy, campaign, messaging | `StoryAgent` + `BrandAgent` |
| Market, customers, competition | `MarketAgent` |
| Data, KPIs, SQL, statistics | `DataAgent` |
| Code, GitHub, Supabase, debugging | `DevAgent` |
| External evidence and research | `ResearchAgent` |
| Acquisition, retention, partnerships | `GrowthAgent` |
| SOPs, process and automation | `OperationsAgent` |
| Complex decision involving several areas | `StrategyAgent` |

A useful habit is simply to tell GRIOT the outcome you need. It should decide which specialists are required.

---

## 5. WHEN should I use GRIOT during a project?

### Before starting

Use GRIOT to test whether the idea is worth doing.

```text
"Challenge this idea. What problem are we really solving, who would pay,
and what evidence would make us stop?"
```

### During planning

Use it to turn an idea into a measurable plan.

```text
"Turn this into a 30-day experiment with assumptions, actions and KPIs."
```

### During execution

Use it to diagnose blockers and coordinate work.

```text
"The feature is built but adoption is weak. Diagnose the bottleneck using
available evidence before proposing more features."
```

### Before major changes

Use it as a second brain.

```text
"Review this production change from business, data, security and technical angles."
```

### After execution

Use it to learn.

```text
"Compare the result with our original hypothesis. What did we learn and
what should we change next time?"
```

---

## 6. WHAT should I ask for when I want better thinking?

These prompts are especially valuable:

```text
"What are we assuming?"

"What evidence supports this?"

"What evidence is missing?"

"What would change your recommendation?"

"Challenge my conclusion."

"What is the real bottleneck?"

"What is the highest-leverage action?"

"What are we doing that looks productive but does not move the KPI?"
```

These questions activate the philosophy behind GRIOT rather than treating it like a content generator.

---

## 7. HOW should I use it for each project?

### SpeakPower

Use GRIOT when you are deciding:

- who the strongest target audience is
- what problem your audience actually feels
- how to position SpeakPower
- which campaigns deserve attention
- which content signals real demand
- which offers can become products/services
- how communications can support revenue and brand equity

Example:

```text
Project: SpeakPower
Analyze our recent content themes and identify the audience problem
that appears to have the strongest commercial potential. Recommend the
next campaign and offer.
```

### Tonninyira

Use GRIOT as a combined product strategist + data analyst + software advisor.

Example:

```text
Project: Tonninyira
Orders are increasing but repeat purchase is flat. Identify the likely
funnel bottleneck, tell me what data we need, propose an experiment,
and suggest the product changes only if the evidence supports them.
```

### CuePointe

Use GRIOT for community growth, tournament design, sponsorship thinking, branding and operations.

Example:

```text
Project: CuePointe
We want stronger player retention across tournaments. Compare loyalty
rewards, rankings, community content and sponsorship incentives. Recommend
the best combination for our current stage and explain the KPI.
```

### UBF / FoB

Use GRIOT for communications strategy, stakeholder messaging, process improvement and responsible AI adoption.

Example:

```text
Project: UBF
Review this workflow and identify repetitive work that AI could assist
with. Separate low-risk automation from decisions that must remain human.
```

---

## 8. WHERE should I allow GRIOT to act?

Think of GRIOT as having levels of authority.

### Level 0 — Observe

It reads data and inspects information.

### Level 1 — Analyze

It diagnoses and recommends.

### Level 2 — Draft

It prepares content, code, SQL, reports or implementation plans.

### Level 3 — Execute with approval

It may make an external change after you approve it.

### Level 4 — Controlled autonomy

It may run pre-approved, reversible, low-risk workflows.

### Keep human approval for:

- money movement
- destructive database operations
- production deployments
- contracts or commitments
- public statements that carry organizational risk
- deletion of important information

The rule is simple:

> **Let GRIOT think broadly; let it act narrowly until trust has been earned.**

---

## 9. HOW should memory be used?

When GRIOT learns something durable, it should be stored as memory rather than re-explained every time.

Good memories:

```text
SpeakPower audiences respond strongly to examples rooted in everyday
Ugandan professional situations.
```

```text
Tonninyira repeat-purchase experiment A failed because the reminder
campaign reached customers too late.
```

Bad memories:

```text
Thomas asked for a campaign on Tuesday.
```

The first is reusable knowledge. The second is temporary conversation history.

---

## 10. HOW to make GRIOT challenge you

Do not train it to be agreeable.

Use prompts like:

```text
"Do not agree with me unless the evidence supports the idea."
```

```text
"Act as a skeptical board member and find the biggest weakness in this plan."
```

```text
"Tell me whether this is actually a strategy or just a list of activities."
```

That is one of the biggest differences between GRIOT and a normal assistant.

---

## 11. What a good GRIOT answer should contain

For important work, expect a response with:

1. **Diagnosis** — what appears to be happening.
2. **Evidence** — what supports it.
3. **Unknowns** — what is still missing.
4. **Options** — realistic paths.
5. **Recommendation** — what GRIOT thinks is strongest.
6. **Action** — what happens next.
7. **Measurement** — the KPI or outcome to watch.
8. **Approval** — whether you need to authorize execution.

If an answer skips evidence and jumps directly to a recommendation, challenge it.

---

## 12. GRIOT weekly rhythm

### Monday — THINK

Ask:

```text
"Review the active projects and identify the 3 highest-leverage priorities for this week."
```

### During the week — EXECUTE

Use GRIOT on specific blockers, decisions and implementation work.

### Friday — MEASURE

Ask:

```text
"What moved this week? What did not? Which activities should we stop, continue or double down on?"
```

### End of month — LEARN

Ask:

```text
"Review our decisions and experiments this month. What patterns are emerging across the portfolio?"
```

This is how GRIOT becomes an operating system rather than another place to ask random questions.

---

## 13. The simple rule to remember

Before opening GRIOT, ask yourself:

> **Am I asking it to produce something, or am I asking it to help me think and move a project forward?**

For simple production, use the simplest tool.

For strategic work, use GRIOT.

And when GRIOT recommends action, always bring the discussion back to:

> **What changes? How will we measure it? What did we learn?**
