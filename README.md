# Project Yuno — AI Agent Orchestration Platform

A local platform for defining, configuring, and executing multi-agent AI workflows. Agents are created and managed through a browser UI, wired together on a visual canvas (React Flow) into directed graphs with conditional edges and configurable feedback loops, and executed through the Goose 1.37.0 runtime. Results flow between agents via a persisted message queue. A human can interact with a connected agent over Telegram, and a trigger phrase can launch a full workflow from the same chat.

---

## Source of Truth Hierarchy

| Priority | Document | Authoritative for |
|---|---|---|
| 1 | `project_yuno.pdf` | Product requirements |
| 2 | `_bmad-output/planning-artifacts/goose-spike-report.md` | Goose 1.37.0 runtime behavior |
| 3 | `SYSTEM_DESIGN.md` | Architectural decisions and boundaries |
| 4 | `BUILD_SPEC.md` | Implementation behavior, contracts, ACs, validation |
| 5 | `_bmad-output/planning-artifacts/stories.md` | Vertical implementation sequence and hour allocation |

When these documents conflict, report the conflict; do not resolve it silently.

---

## Architecture Overview

The system is a **modular monolith**: one FastAPI process hosts the REST API, workflow orchestrator, background worker, SSE endpoint, APScheduler, and Telegram poller. Goose 1.37.0 is the agent runtime, accessed via its ACP (Agent Client Protocol) server — a JSON-RPC 2.0 + SSE interface. The platform never calls an LLM directly; an `AgentRuntimeAdapter` ABC isolates all runtime coupling. SQLite provides zero-setup local persistence.

```mermaid
graph TB
    subgraph Browser["Browser (React SPA · :5173)"]
        AM[Agent Manager UI]
        WB[React Flow Builder]
        LM[Live Monitor]
    end

    subgraph Backend["FastAPI Backend · :8000"]
        API[REST API Layer]
        SVC[Service Layer]
        ORCH[Workflow Orchestrator]
        GATE[Approval Gate]
        QUEUE[asyncio Queue]
        WORKER[Worker Loop]
        SSE[SSE Endpoint]
        SCHED[APScheduler 3.x]
        TG[Telegram Poller]
        ADAPT[AgentRuntimeAdapter]
    end

    subgraph Goose["Goose 1.37.0 · :3284"]
        ACP[ACP Server — JSON-RPC 2.0]
        EXT[Extensions: developer + per-session MCP]
    end

    subgraph DB["SQLite · ./data/yuno.db"]
        TABLES[(agents · workflows · runs · tasks · messages · events)]
    end

    subgraph External
        TG_API[Telegram Bot API]
        LLM[Anthropic API — native provider]
    end

    Browser -->|HTTP REST| API
    Browser -->|SSE stream| SSE
    API --> SVC
    SVC --> ORCH
    ORCH --> GATE
    GATE --> QUEUE
    QUEUE --> WORKER
    WORKER --> ADAPT
    ADAPT -->|JSON-RPC POST /acp + session SSE| ACP
    ACP --> EXT
    ACP --> LLM
    SCHED --> ORCH
    TG -->|long polling| TG_API
    TG --> SVC
    WORKER -->|sendMessage| TG_API
    SVC --> DB
    ORCH --> DB
    WORKER --> DB
```

> Mermaid syntax inspected manually. No local validator available.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Backend runtime |
| Node 20+ | Frontend build only |
| Goose CLI 1.37.0 | `brew install block-goose-cli` |
| `ANTHROPIC_API_KEY` | Native provider required — CLI-bridge providers (claude-code, gemini-cli) are not supported |
| Telegram bot token | Create via @BotFather |
| Telegram chat_id | Your operator chat ID for the demo channel |

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# Goose runtime — native provider required
GOOSE_PROVIDER=anthropic
GOOSE_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...
GOOSE_PORT=3284

# Telegram
TELEGRAM_BOT_TOKEN=...
DEMO_TELEGRAM_CHAT_ID=...

# Application
DATABASE_URL=sqlite+aiosqlite:///./data/yuno.db
LOG_LEVEL=INFO
SEED_OFFLINE_DEMO=false
```

---

## Setup and Run

```bash
# One-time setup (non-interactive)
make setup

# Start all services
make dev
```

`make setup` installs Python and Node dependencies, creates the database, and seeds six agents and two workflow templates. `make dev` starts Goose (`:3284`), the FastAPI backend (`:8000`), and the Vite frontend (`:5173`), then runs a health preflight.

```bash
# Optional: verify Goose ACP integration before building on it
make smoke-goose
```

`make smoke-goose` opens one real ACP session with the native provider, asserts a `tool_call` event is captured, and writes an artifact to disk. Run this first on Day 1 before any app code depends on the adapter (AC-4).

---

## Runtime Choice

**Goose** was selected over OpenCode and OpenClaw (see `SYSTEM_DESIGN.md` ADR-001). Key reasons:

- ACP server with sessions, live-switchable modes (`auto`/`approve`/`smart_approve`/`chat`), and session-scoped SSE streaming
- Recipes as a validated per-agent definition format
- Native per-turn usage reporting (feeds the token/cost requirement)
- Per-session MCP extension injection via `session/new mcpServers`
- Native cron scheduler and Telegram gateway — both verified in a local spike before implementation began

**OpenCode** is a viable alternative — it ships `opencode serve` with an HTTP SDK designed for programmatic driving. It was not chosen only because the Goose spike was already complete and restarting integration risk from zero was not justified within the two-day window.

**OpenClaw** has overlapping built-in features (scheduler, memory, channels) that would blur the PRD's requirement that the *platform* own configuration UI and persistence.

The platform fails loudly if Goose is unreachable — there is no non-Goose fallback. The compliant contingency within the same runtime is `CliGooseAdapter` (`goose run --recipe --params`), built on demand only if the ACP smoke gate fails.

---

## Demo Workflow Summary

The recorded demo follows eight beats:

1. **Agents page** — six seeded agents (Coder, Reviewer, Deployer, Research, Compliance, Analyst) with five config dimensions each; Telegram channel badge on Research
2. **Edit memory live** — edit a Research agent memory fact (corridor default, visible in beat 8)
3. **Builder-modification** — load Dev Pipeline template, edit an edge condition, bump loop max-iterations, swap a node, save as new workflow
4. **Run + approval** — run the modified pipeline; watch tool calls; REJECTED loop fires once; APPROVED; Deployer approval gate pauses the run; click Approve; run completes with token totals
5. **Remittance Comparison** — load `remittance_comparison` template; inspect Research → Compliance → Analyst graph with KTD6 sentinel edges
6. **Telegram trigger (primary path)** — send `run remittance: $500 cash to Bogotá`; watch Research → Compliance CLEARED → Analyst RECOMMENDATION in one clean pass; phone buzzes with the recommendation summary
7. **Expand run row** — full conversation trail, tool calls, per-task tokens
8. **Conversational memory** — send a plain Telegram message; reply reflects the edited memory fact

---

## Remittance Comparison Workflow

**Demo rules engine only — not legal or regulatory compliance advice.**

Three-role pipeline replacing the old Research Pipeline template: **Research** gathers provider quotes, **Compliance** runs deterministic rules screening (no scoring, no recommendations), **Analyst** scores providers, writes `reports/transfer_comparison.md`, and produces Telegram-ready text.

### Why Compliance is separate

Compliance is a **scripted adapter** (`ComplianceAdapter`) behind the same `AgentRuntimeAdapter` ABC as Goose — it runs the rules engine in pure Python with `tokens_total=0`. The Analyst never runs on a FLAGGED transfer. This separation keeps screening deterministic and testable; it is a **demo rules engine**, not legal advice.

### Data sources

- **Fixture mode (default in tests and offline demo):** Research loads `backend/fixtures/transfer_fixture.json` and labels `data_source: "fixture"`. Live rates are never invented.
- **Live mode (Goose Research agent):** Research may call `read_file` on the fixture or a future live hook; `data_source` is labeled accordingly. Correctness in unit/integration tests never depends on the LLM.

### Routing tokens (KTD6)

Graph edges match **anchored sentinels** on line 1 of agent output — e.g. `COMPLIANCE=CLEARED`, `COMPLIANCE=FLAGGED`, `ANALYST=RECOMMENDATION`, `ANALYST=NEEDS_MORE_DATA` — not bare words like `CLEARED` (which would substring-match inside FLAGGED issue prose and fail open).

### Scoring model (Analyst)

Weighted min-max normalization: **50%** recipient value (`cop_received`), **30%** location convenience (cash sends only), **20%** speed. Digital sends equalize the location term. Tie-break: higher `cop_received`.

### Telegram integration

| Status | Detail |
|---|---|
| **Implemented (U1–U9)** | Seed graph, domain logic, Compliance adapter, worker routing, terminal output contracts, deterministic tests |
| **Deferred (S3)** | Inbound poller routing on `run remittance:` prefix, outbound `bot.send_message` on terminal completion, `channel_outbound` persistence |

The Research agent's `channel_connections` row points `trigger_workflow_id` at the remittance workflow. Outbound send is owned by the platform worker (not a Goose tool).

### Worked example — cleared ($500 cash, Austin → Bogotá)

**Request (Telegram):**
```
run remittance: $500 cash to Bogotá
```

**Terminal response (Analyst `telegram_message`):**
```
RECOMMENDATION: MoneyGram
Fee $9.99 · Rate 4,155 COP/USD · You receive 2,035,992 COP
Pickup: Walmart Supercenter, 3.8 mi (Daily 7am-11pm)
Runner-up: Western Union — $3.00 higher fee but 25 COP/USD better rate
Full report: reports/transfer_comparison.md
```

### Worked example — FLAGGED ($3500 AML threshold)

**Request:**
```
run remittance: $3500 cash to Bogotá
```

**Terminal response (Compliance output; Analyst never runs):**
```
COMPLIANCE=FLAGGED
Cash send amount $3500 exceeds the configured $3000 AML reporting threshold.
```

*(S3 may wrap this in a user-facing alert; the routing sentinel stays on line 1.)*

### Known limitations

- No real OFAC/sanctions feed — rules come from `backend/fixtures/compliance_rules.json` only
- No live-rate guarantee — fixture data is clearly labeled demo pricing
- **Sender `previously_flagged` is LLM-asserted in live mode** — Research authors the brief; Compliance fail-closes if the field is missing, but cannot detect a hallucinated `false`
- `sender_profile` PII is not redacted in logs or reports
- Per-run cost guardrails deferred (no `max_cost_per_run` column yet)

### Production hardening notes

- Wire authoritative sender KYC from an identity store into the brief (not agent memory)
- Replace substring edge matching with anchored parsing at the orchestrator layer
- Add real compliance data feeds and legal review before any production use

---

## Tests and Validation

> Tests are created during implementation. This section will be updated to show actual commands and results.

```bash
# Run the default test suite (remittance + workflow + agent tests)
cd backend && pytest

# Run the opt-in live Goose integration test (requires ANTHROPIC_API_KEY and running goose serve)
cd backend && pytest -m live
```

**Critical-path tests (AC-3):**
- `test_agent_create.py` — Agent CRUD + context assembly
- `test_workflow_run_e2e.py` — 2-agent flow, mocked adapter, approval branch
- `test_message_delivery.py` — persist + deliver + ordering

**Manual validation checklist (Day 2):**
- [ ] AC-1: builder edit honored by next run
- [ ] AC-2: template loaded, modified, saved, run succeeds
- [ ] AC-5: Telegram reply reflects edited memory fact
- [ ] AC-6: 1-minute schedule fires in monitor without manual action
- [ ] AC-7: fresh-clone `make setup && make dev` works
- [ ] AC-8: full live rehearsal passes before recording

---

## How to Add a Workflow Template

> Detailed instructions will be finalized in S6. Placeholder below.

1. Design your workflow as a directed graph: identify agent nodes and conditional edges
2. Insert rows into `workflows`, `workflow_nodes`, and `workflow_edges` (or duplicate an existing workflow via `POST /workflows/{id}/duplicate` and edit in the builder)
3. Set `template_key` to a unique string if the template should appear in the Load Template picker
4. Edge `condition` values are free-form substring-match strings (e.g. `"APPROVED"`, `"always"`). Remittance template uses KTD6 sentinels: `COMPLIANCE=CLEARED`, `ANALYST=NEEDS_MORE_DATA`.
5. Loop edges point a `to_node_id` back to an earlier node in the seeded layout; set `max_iterations` to cap the loop

---

## How to Add a Messaging Channel

> Detailed instructions will be finalized in S6. Placeholder below.

1. Implement a class with `start()` and `send_message(chat_id, text)` methods following the Telegram poller's interface
2. Start it inside the FastAPI lifespan context manager alongside the Telegram poller
3. Insert a `channel_connections` row with `channel_type` set to your new channel name
4. The worker's outbound path and the UI's channel badge system are channel-type-agnostic

---

## Known Limitations

- **Tool access is at extension granularity**, not per-tool — the `developer` builtin gives an agent both file edit and shell access
- **Memory is operator-written only** — agents cannot write their own memory entries in this version
- **No run resumption** — a backend restart marks in-flight runs as failed; the PRD does not require resumption
- **Single in-process worker** — no distributed queue; not designed for concurrent multi-user load
- **Missed schedule executions** not replayed after downtime
