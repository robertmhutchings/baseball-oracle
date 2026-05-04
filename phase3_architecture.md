# Phase 3 Architecture

**Date:** 2026-04-29
**Status:** Approved, pending implementation
**Supersedes:** None (this is the foundational Phase 3 design document)

## Purpose of this document

Phase 2 closed 2026-04-29 with the full 1907-2023 Retrosheet corpus loaded into PostgreSQL and verified across three layers. Phase 3 builds the agent layer that turns the database into a natural-language Q&A product.

This document captures the architectural decisions made during the Phase 3 design conversation (2026-04-29), the reasoning behind each, and the implementation plan. It exists so that:

- Future implementation sessions have a clear reference for "what are we building and why"
- Anyone picking up the project (including future-Robert after a break) can understand the decision space without reconstructing it
- Decisions can be revisited deliberately rather than drifted away from accidentally

This is a living document. If a decision changes during implementation, update it here with the date and reasoning.

---

## 1. Project framing

### What we're building

A natural-language Q&A system for historical baseball, sourced from Retrosheet 1907-2023 game logs. The user types questions in plain English; the system answers with precision, context, and citations — feeling like talking to a knowledgeable baseball historian who is also a data analyst.

### v1 scope (this phase)

Laptop-only deployment. Runs on Robert's $300 Windows laptop. PostgreSQL hosts the data. A Python agent processes questions via the Anthropic API. A minimal web UI on localhost provides the interface. Demo experience is "share screen in Teams/Webex, type questions into a browser tab."

**Not in scope for v1:**

- Public hosting / baseballoracle.com (deferred to Phase 4)
- User accounts, persistent sessions, multi-user support
- Mobile-responsive design (desktop-first)
- Wikipedia RAG layer for narrative enrichment (deferred — see §10)

### Success criteria

The agent answers the 25 benchmark questions from the brief well, where "well" is defined per-question:

- For verifiable questions (canonical answers exist): correct numerical answer
- For unverifiable questions (no canonical answer): sound process — honest decline if unanswerable, appropriate caveats if uncertain, no hallucination
- For all questions: response style consistent with the brief's "research partner, not query translator" tone

The shippable milestone is "I can run a command on my laptop, ask Baseball Oracle questions in a browser, and get well-framed answers I'd be willing to demo to a colleague."

---

## 2. Architecture decisions

### 2.1 Agent loop structure

**Decision:** Agentic loop (LLM with tools) rather than fixed pipeline.

**Reasoning:** The 25-question gauntlet spans simple aggregations (Q1, Q11) to complex multi-step reasoning (Q14, Q19). A fixed pipeline would either over-engineer the simple cases or fail at the complex ones. Agentic loop lets the agent break problems into steps as needed.

**Implementation:** Anthropic SDK's tool-use feature directly. ~50-100 lines of code for the loop itself. The model receives tool definitions, decides when to call them, the agent code handles tool execution and feeds results back, loop continues until the model produces a final response.

### 2.2 Tools

**Decision:** Hybrid approach — start with 4 tools, grow specialized tools as patterns emerge.

**v1 tools:**

- `run_sql(query: str)` — direct SQL access against the retro schema
- `lookup_player(name: str)` — wraps player disambiguation logic per §9.1
- `lookup_team(name: str)` — wraps team/franchise/era disambiguation
- `ask_user(question: str)` — pauses the loop to ask the user for clarification

**Reasoning:** Direct SQL access maximizes flexibility for the hard questions (RISP performance, multi-decade arcs, etc.). Specialized tools wrap the disambiguation logic because getting player/team identification wrong is a high-cost failure (wrong-answer-that-looks-right). Starting minimal lets us build to v1 quickly and extract specialized tools as we observe agent behavior.

**Future tools** (to be added based on observed patterns):

- Specialized aggregations (career stats, season stats, head-to-head matchups)
- Wikipedia RAG (Phase 3+)
- Possibly a "describe schema" tool if the agent needs schema lookup more than once

### 2.3 Database access

**Decision:** Full SQL access via the `run_sql` tool, with safety guardrails.

**Guardrails:**

- **Read-only PostgreSQL role.** Agent connects with credentials that have SELECT on the retro schema only. No INSERT, UPDATE, DELETE, DROP, or DDL of any kind.
- **Query timeout.** SQL queries that take >30 seconds return a timeout error to the agent, which can rethink its approach.
- **Result size cap.** Queries returning >1,000 rows (configurable) get truncated; agent is told the result was truncated.

**Reasoning:** Full access is necessary for the situational/clutch questions in the 25-question list. The guardrails ensure that "agent has full access" doesn't translate to "agent can break things" — read-only role is structural, not behavioral.

**Setup steps (one-time):**

```sql
CREATE ROLE baseball_oracle_agent WITH LOGIN PASSWORD '<chosen>';
GRANT USAGE ON SCHEMA retro TO baseball_oracle_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA retro TO baseball_oracle_agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA retro GRANT SELECT ON TABLES TO baseball_oracle_agent;
```

Connection settings include `statement_timeout = '30s'` for the agent's session.

### 2.4 System prompt

**Decision:** All-in prompt (no lazy loading). Separate agent-flavored prompt document, manually maintained, mirroring CLAUDE.md content. Accept drift risk for v1.

**Three layers in the prompt:**

1. **Identity and behavior** — persona, response style principles (§8 dynamism), era-aware calibration (§9.4), unanswerable-question protocol (honest decline with pivot)
2. **Tools** — auto-generated from tool definitions by the SDK
3. **Schema knowledge** — schema overview, the 28 quirks from CLAUDE.md §4, common query patterns, transformed into directive form (rules and imperatives) rather than narrative prose

**Reasoning:** The schema is bounded enough to fit comfortably in a system prompt. "Forgetting a quirk" is a high-cost failure (silent wrong answer); keeping all rules visible every turn prevents this. LLM API costs at this scale are negligible. Simpler debugging.

**On the separate doc + drift risk:** Building a programmatic derivation from CLAUDE.md upfront is yak-shaving. We'll write the agent prompt manually now, accept that CLAUDE.md and the agent prompt could drift, and only build derivation tooling if drift becomes an observed problem.

### 2.5 Disambiguation flow

**Decision:** Tiered approach mirroring CLAUDE.md §9.1, with the agent applying judgment within the frame.

**The tiers:**

- **1 match** → answer directly (no ambiguity)
- **2-5 matches:**
  - For stat questions: surface all interpretations ("There are two Griffeys: Sr. hit 14 HRs in 1990, Jr. hit 22 HRs in 1990")
  - For narrative questions: ask the user
- **6+ matches:** ask the user to narrow ("There are 47 Smiths in the data. Can you give me a first name or era?")

For conceptual ambiguity (e.g., "best clutch hitter"): usually ask, sometimes multi-answer the obvious interpretations.

For era ambiguity for teams: combine — surface the franchise interpretation while answering ("Washington in the 1920s was the Senators (later became Twins). They went...").

**Mechanism:** The agent decides when to call `ask_user`. The user's response becomes the next turn's input. This means the agent loop must handle multi-turn conversations naturally — some questions complete in one round, some take multiple rounds.

### 2.6 Unanswerable questions

**Decision:** Honest decline, with caveat-and-pivot to what can be answered.

**Example shape:** "I can't answer this from the Retrosheet data — WAR isn't included, and trade history isn't in my dataset. I can tell you about specific players' performance before and after specific dates if you have someone in mind, but I can't compute WAR or compare trades systematically."

**Reasoning:** Aligns with the brief's §7 quality bar ("Never hallucinate statistics. If the data doesn't support a confident answer, say so") and avoids the failure mode of confidently-wrong answers that erode trust.

**Categories of unanswerable from Retrosheet alone:**

- WAR, HOF voting %, salary data
- Statcast metrics (pre-2015 entirely; varies after)
- Trade history and transaction data
- Things requiring Wikipedia RAG (deferred to later phase)

### 2.7 Response synthesis

**Decision:** Single agent writes its own response (Architecture 1 from the design discussion), with a clear seam to graduate to two-stage synthesis later if needed.

**Reasoning:** Simpler to build, fewer LLM calls per question, easier to debug. The agent that gathered the data has the full context needed to write a good answer. Graduating to a separate synthesis stage is an option if response quality issues emerge that gathering-loop attention can't fix.

**The "clear seam":** Response-writing instructions live in a clearly delineated section of the system prompt. If we ever need to extract synthesis into a separate step, the relevant prompt content moves cleanly.

### 2.8 Trace transparency

**Decision:** Tool-call tracing built in from v1. Minimal UX initially.

**Implementation:** Every tool call and result is logged during the agent loop. The web UI shows an expandable "How did I get this answer?" section that surfaces the trace — initially as raw text, can be polished later.

**Reasoning:** Trivially small extra work given the SDK exposes tool calls naturally. Critical for debugging during development. Aligns with the brief's UX expectation. Free to add now; expensive to retrofit later.

### 2.9 Tech stack

| Component | Choice | Reasoning |
|---|---|---|
| Language | Python 3.12 | Existing codebase is Python; LLM ecosystem is mature in Python; PostgreSQL via psycopg already in use |
| LLM API | Anthropic SDK directly | No framework — direct API access keeps the agent loop visible and debuggable. Frameworks like LangChain add abstraction without proportionate benefit for a focused project |
| Web framework | FastAPI | Async support matters for LLM API call latency; cleaner than Flask for JSON request/response patterns |
| Database client | psycopg 3.x | Already in use for ingest; well-supported |
| Frontend | Plain HTML/CSS/JS | No framework needed for v1; chat interface is simple enough that a build system would be overkill |

### 2.10 Codebase shape

```
C:\BaseballOracle\
├── agent/                       # Agent code
│   ├── __init__.py
│   ├── main.py                  # Agent loop entry point
│   ├── tools.py                 # Tool definitions
│   ├── prompts.py               # System prompt construction
│   ├── db.py                    # DB connection helpers (read-only role)
│   ├── trace.py                 # Tool-call logging for transparency
│   └── config.py                # API keys, DB credentials, model selection
│
├── eval/                        # Evaluation infrastructure
│   ├── __init__.py
│   ├── benchmarks.py            # The 25 questions + expected answers/behavior
│   ├── runner.py                # Runs agent against benchmarks, scores results
│   └── results/                 # Captured runs over time
│
├── ui/                          # Interface code
│   ├── server.py                # FastAPI server
│   ├── static/
│   │   ├── index.html           # Chat interface
│   │   ├── style.css            # Baseball-themed styling
│   │   └── app.js               # Frontend logic
│   └── cli.py                   # CLI fallback for quick testing
│
├── ingest/                      # (existing) Phase 2 ingest scripts and scans
├── schema/                      # (existing) schema.sql, migrations
├── data/                        # (existing) Retrosheet CSVs
├── data_corrections/            # (existing) Correction logs
├── scratch/                     # (existing) Verification queries
├── CLAUDE.md                    # (existing) Project context
├── phase3_architecture.md       # This document
├── .env                         # (existing) DB password, plus new keys
└── requirements.txt             # NEW — Python dependencies
```

**New `.env` entries:**

- `ANTHROPIC_API_KEY` — for the agent's LLM calls
- `BASEBALL_ORACLE_DB_USER` and `BASEBALL_ORACLE_DB_PASSWORD` — read-only DB role credentials

Existing entries unchanged. The agent connects with the read-only role; ingest scripts continue to use the postgres superuser.

### 2.11 Interface

**Decision:** Minimal web UI on localhost, FastAPI-based, baseball-themed.

**v1 features (in scope):**

- Single-page chat interface
- Text input + send button
- Conversation visible above input
- Loading indicator during agent processing
- Trace expand/collapse ("How did I get this answer?")
- Baseball-themed styling per the brief — scoreboard aesthetic, dark background, clean typography

**v1 non-features (deferred):**

- User accounts / login
- Persistent conversation history across sessions
- Multiple concurrent users
- Mobile-responsive layout
- Conversation export/sharing

**Why localhost web UI rather than CLI:** A visual interface feels meaningfully better than a terminal even for personal use; the demo experience over Teams is genuinely nicer; the upgrade path to public hosting (Phase 4) is "run the same code on a cloud server" rather than "rebuild the interface."

### 2.12 Evaluation framework

**Decision:** Hybrid — automated structural/process checks plus manual review for quality and verifiable answers.

**Three categories of automated checks** (run on every response):

1. **Structural correctness:** Did the response contain the answer (a number, a list, a yes/no)? Did it cite which data was used? Did it surface assumptions when they matter? Did it caveat era issues if relevant?
2. **Process correctness:** Did the agent use the right tools? Did it apply the necessary filters (`stattype='value'`, `gametype='regular'`)? Did it correctly disambiguate when needed? Did it gracefully decline when it should have?
3. **Performance characteristics:** Reasonable number of agent turns? Reasonable SQL execution time? Cost per question within bounds?

**Two categories of manual review:**

1. **Verifiable questions** (Q1, Q2, Q11, etc.): Does the final answer match the expected answer?
2. **Quality judgment** (any question, especially unverifiable ones): Read the response, judge whether it sounds like a knowledgeable baseball historian.

**Special handling for unverifiable questions:** When neither expected-answer matching nor confident eyeball is possible, judge by process. An honest decline with useful pivot is the correct response. A confident answer to a question Retrosheet can't actually answer is a hallucination, even if it sounds plausible.

**v1 implementation:**

- Start with 8-10 of the 25 questions wired up, including the verifiable ones from Phase 1 plus a few unverifiable ones to test the framework against both shapes
- Run `python -m eval.runner` to exercise the agent against benchmarks, capture responses + traces
- Output report: pass counts, flagged items requiring manual review
- Iterate the framework alongside the agent

Expected answers populated as: partial pre-population from CLAUDE.md / brief / Phase 1 verified results; the rest captured as we go on first pass.

---

## 3. Implementation plan

The plan is sequenced so that something demoable exists as early as possible, then quality grows from there. Order of work:

### Phase 3A: Foundation (target: 1-2 sessions)

- Create the read-only DB role and verify connectivity from a Python script
- Build the basic agent loop in `agent/main.py` — Anthropic SDK, single tool (`run_sql`), simple system prompt, CLI invocation
- Test against 2-3 simple questions (Jeter May 1998 HRs, Ruth career HRs) to verify the loop works end-to-end
- Add the other three tools (`lookup_player`, `lookup_team`, `ask_user`)

**Milestone:** Can ask Baseball Oracle simple questions via CLI and get reasonable answers.

### Phase 3B: System prompt and quirks (target: 1-2 sessions)

- Write the agent-flavored schema prompt — transform CLAUDE.md §3-4 content into directive rules
- Add response style instructions (§8 dynamism, §9.4 era calibration, honest-decline protocol)
- Test against the 5 Phase 1 verified questions to verify quirks are correctly applied

**Milestone:** The 5 Phase 1 questions return correct answers with appropriate framing.

### Phase 3C: Web UI (target: 1-2 sessions)

- Build FastAPI server with `/api/ask` endpoint that runs the agent
- Build minimal HTML/CSS/JS frontend — chat interface, baseball aesthetic
- Wire up trace display (expandable "How did I get this answer?" section)

**Milestone:** Robert can demo Baseball Oracle in a browser tab, share screen over Teams.

### Phase 3D: Eval framework (target: 1-2 sessions)

- Build `eval/benchmarks.py` with the 25 questions, partial expected answers
- Build `eval/runner.py` with automated checks and manual-review flagging
- Run the full 25-question gauntlet, identify gaps, capture results

**Milestone:** Quantified view of agent quality. Iteration becomes data-driven.

### Phase 3E: Iterate to quality (target: ongoing)

- Address gaps surfaced by the eval — likely a mix of prompt tweaks, additional tools, edge cases in disambiguation
- Add specialized tools as patterns emerge from observed failures
- Polish response quality — does it sound like a baseball historian? Are caveats well-placed? Is the tone right?

**Milestone:** Robert is genuinely happy with the agent's responses across the full 25 questions. Phase 3 is complete in spirit.

---

## 4. Open questions and deferred decisions

### Open

- **Specific Claude model selection:** Sonnet vs. Opus — affects cost and quality. Decision deferred to first implementation session; will compare on a few benchmark questions and pick. Default starting point: Claude Sonnet 4.6 (cheaper, fast, likely sufficient for v1).
- **Frontend styling specifics:** "Baseball-themed scoreboard aesthetic" leaves room for interpretation. Will iterate during Phase 3C with Robert's reactions.

### Deferred to later phases

- **Wikipedia RAG layer** for narrative enrichment (per brief §4.3). Will be added after v1 is working — agent layer can be enhanced incrementally without rebuilding.
- **Public hosting** at baseballoracle.com (Phase 4). Architecture choices made here support this path: agent code is decoupled from interface, the FastAPI server can run on a cloud host with no code changes.
- **Session persistence** (conversation history that survives browser refresh). Reasonable v2 feature; out of v1 scope.
- **Mobile-responsive design.** Out of v1 scope; desktop-only is fine for the demo experience.
- **Transactions data** for trade-related questions. Currently flagged in brief §8 note as Q19/Q20 limitations. Could be added if we find a clean source.

### Risks to monitor

- **Drift between CLAUDE.md and the agent prompt.** We've accepted this for v1. If we observe drift causing wrong answers, we'll invest in derivation tooling.
- **Agent forgets quirks despite system prompt.** Possible if the schema knowledge in the prompt grows too large. Mitigation: extract to specialized tools (Design B direction).
- **Cost overruns during eval iteration.** Running 25 questions × multiple turns × LLM calls at full prompt size could add up. Mitigation: track cost during eval runs, optimize prompt size if needed.

---

## 5. Decision log

Decisions are listed by topic with date approved.

| Date | Topic | Decision | Rationale |
|---|---|---|---|
| 2026-04-29 | v1 scope | Laptop-only | Hobby project, $300 laptop, Teams/Webex demo path |
| 2026-04-29 | Agent loop | Agentic (LLM with tools) | Range of question complexity in 25-question gauntlet |
| 2026-04-29 | Tools | Hybrid: 4 tools to start, grow as patterns emerge | Balance of v1 speed vs. correctness |
| 2026-04-29 | DB access | Full, with read-only role + timeout + size cap | Hard questions need plays-table access; safety via role |
| 2026-04-29 | System prompt | All-in, separate agent-flavored doc | Schema fits in prompt; drift risk acceptable for v1 |
| 2026-04-29 | Disambiguation | Tiered per CLAUDE.md §9.1 | Aligns with already-articulated design |
| 2026-04-29 | Unanswerable questions | Honest decline with pivot | Brief §7 quality bar |
| 2026-04-29 | Response synthesis | Single agent (Architecture 1) | Simpler to v1, seam in place if we need to graduate |
| 2026-04-29 | Trace transparency | Built in from v1 | Cheap to add now; valuable for debugging |
| 2026-04-29 | Tech stack | Python, Anthropic SDK direct, FastAPI | Existing toolchain, minimal abstraction |
| 2026-04-29 | Interface | Minimal web UI on localhost | Better than CLI for demo; upgrade path to public hosting clean |
| 2026-04-29 | Eval | Hybrid (automated checks + manual review) | Some questions Robert can't eyeball; need process-correctness checks |
| 2026-04-29 | Eval pre-population | Partial — fill in canonical answers now, rest as we go | Don't block framework on perfect knowledge |

---

## 6. Cross-references

- **Project context:** `CLAUDE.md`
- **Original spec:** `baseball_oracle_brief.docx` (the developer brief; defines the 25 benchmark questions)
- **Phase 1 deliverables:** `scratch/q01-q05.sql` (the 5 verified queries)
- **Phase 2 deliverables:** `ingest/phase2_smoke_test_plan.md`, `data_corrections/`, schema migrations, scan scripts
- **Phase 2 verification artifacts:** `scratch/l1_*.sql`, `l2_*.sql`, `l3_*.sql`

When implementation begins, this document should be referenced at the start of each session to ensure work stays aligned with the architecture. Any decision change must be logged in §5 with date and reasoning.
