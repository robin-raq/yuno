# Project Yuno — Implementation Stories (6)

**Basis:** SYSTEM_DESIGN.md v3.0 (architecture) · BUILD_SPEC.md v1.0 (binding behavior and ACs) · implementation-readiness-report.md (READY WITH CONDITIONS) · goose-spike-report.md
**Authority:** architecture references → SYSTEM_DESIGN.md; behavioral contracts and ACs → BUILD_SPEC.md.
**Budget (three categories):** two ~12h days = ~24h wall clock, split **18.5h feature implementation (S1–S5) + 3.0h mandatory release/submission work (S6) + 2.5h genuine unallocated contingency**. S6 is *not* contingency — it is required submission work (fresh-setup verification, README, integrated validation, rehearsal, recording, cleanup). The 2.5h contingency is the only true buffer for integration failures and overruns. Time limits below are hard caps — when a cap hits, the story's scope-cut rule fires; cuts reduce *implementation ambition*, never PRD must-haves.
**UI policy (amended):** browser UI is built incrementally inside the slice that produces its data — no late integration cliff. S1 ships a plain read+run shell, S2 a live run view, S4 the configuration controls; S5 is the visual workflow builder plus a single whole-app polish pass.
**Global rule:** every story ends with its tests green and a commit. The recording (S6) is the 40% — S1–S5 caps exist to protect it.
**Prerequisites before S1 hour 0 (user-supplied):** funded `ANTHROPIC_API_KEY` in `.env`; Telegram bot token from @BotFather + operator chat_id; `goose --version` → 1.37.0 (already installed during spike); Python ≥3.11, Node ≥20.

---

## S1 — Verified runtime spine (agents that really run)
**Day 1 morning · Time limit: 5.5h · Depends on: prerequisites only**

**User-visible value:** From a plain browser page, select a seeded agent, submit a task, and watch it execute a real task with a real tool through Goose — the platform's existence proof, visible without curl.

**Scope:** Hour-0 smoke gate (ACP session with native `anthropic` provider → capture ≥1 `tool_call` event + on-disk artifact; verify `session/close`; pivot decision by end of hour 1). Repo scaffold; SQLite schema via `create_all` (incl. nullable `run_id`/`node_id` + `source` on agent_tasks); `make setup`/`make dev` (non-interactive, **now installs + serves the Vite frontend too**); `AgentRuntimeAdapter` ABC + `AcpGooseAdapter` (initialize → session/new → session-scoped SSE → prompt with assembled context → event mapping → usage capture); Agent CRUD API with all six PRD fields (name, role, system prompt, model, tool access, channels); single-agent task execution persisting `execution_events`. **Minimum React shell (intentionally plain, no styling): Vite+React app; one page that lists seeded agents in a dropdown, a task textarea + Submit button (`POST /agents/{id}/tasks`), and a result panel showing the persisted final result + a flat list of basic `execution_events`.**

**Acceptance criteria:** BS AC-4 (smoke gate); `POST /agents` → row with six fields; `POST /agents/{id}/tasks` → task runs through Goose, a `tool_call` event and token usage are persisted; `make setup && make dev` brings up backend **and** the browser shell from a fresh clone; **the shell submits a task and renders the persisted result + events.**
**Required tests:** `test_agent_create` (API→DB), `test_adapter` (recorded-frame fixtures from the real smoke capture).
**Demo evidence:** browser shell: pick a seeded agent, submit a task, watch it write a file via the developer extension; result + event rows render in the page (DB/API as backup proof).
**Scope-cut rule:** if `tool_call` is not captured on ACP by end of hour 1 → pivot to `CliGooseAdapter` (`goose run --recipe --params`, spike-verified) behind the same ABC; ACP becomes the contingency. If the shell overruns → it degrades to a single hardcoded-agent submit form (no dropdown); never cut the smoke gate, the CRUD fields, or a working browser submit→result path.

## S2 — Multi-agent workflow with persisted A2A messaging
**Day 1 afternoon · Time limit: 4h · Depends on: S1**

**User-visible value:** In the browser, trigger a workflow and watch two-plus agents complete a real task together — output handoff, feedback loop, conclusion — streamed live, with the full conversation trail visible.

**Scope:** workflows/nodes/edges API; orchestrator with free-form contains-match edge conditions + `always`; feedback-loop cap (2, force-complete on 3rd with `forced_complete=true` per BS §9.3 — *not* a failure); asyncio.Queue worker; `agent_messages` persisted (A→B output, B→A feedback); **fully build and exercise ONE template end-to-end — the Dev Pipeline (Coder→Reviewer→(rejected loop|approved→Deployer)); seed the second (Research→Analyst→Publisher w/ NEEDS_MORE_DATA loop) but defer its run-validation to S6**; SSE endpoint streaming `execution_events`. **Minimum browser run view (plain, reuses S1 shell): a button to start a seeded workflow run, an `EventSource` consuming the run's SSE stream, and a list rendering both agent tasks, persisted A2A messages in order, feedback-loop iteration markers, and the final run status.**

**Acceptance criteria:** BS AC-5 (dev-pipeline run executes with one rejected iteration then completes); message trail for a run retrievable in order; **the Dev Pipeline template loads and runs end-to-end (second template seeded, run-validated in S6)**; **the browser run view shows the live run end-to-end (both tasks, ordered messages, the loop iteration, final status) over SSE.**
**Required tests:** `test_workflow_execution` (2-agent flow, mocked adapter), `test_message_delivery` (persist + deliver + order).
**Demo evidence:** browser: start the dev-pipeline run, watch it reach `workflow_completed` with the loop iteration and ordered message trail rendered live.
**Scope-cut rule:** second-template run-validation is already deferred to S6 (baseline, not a cut). If still overrun → the run view degrades to a poll-on-refresh list (SSE wiring slips to contingency). Never cut the loop cap, conditions, or message persistence.

## S3 — Live Telegram channel
**Day 1 evening · Time limit: 2.5h · Depends on: S1 (S2 for trigger phrase)**

**User-visible value:** A human opens Telegram, messages the agent, and gets a real reply shaped by its persona and memory; a trigger phrase launches a workflow from the same chat.

**Scope:** python-telegram-bot v21+ long polling in FastAPI lifespan; single consumption path (prefix rule on ChannelConnection → workflow trigger | else conversational run-less task `source='conversational'`); reply assembled from persona + memory + skills; outbound send by worker after publisher/terminal node; inbound/outbound persisted as channel messages in the trail; channel badge data on agents.

**Acceptance criteria:** BS AC-8 (live round-trip: message → real Goose-executed reply); reply visibly cites a seeded memory fact; `run research: X` launches the research pipeline and the result lands back in the chat; all channel messages visible via API for the UI trail.
**Required tests:** `test_telegram_routing` (mocked Bot API; asserts run-less conversational task + trigger path).
**Demo evidence:** phone screen + monitor side-by-side: live conversation, then trigger phrase starting a run.
**Scope-cut rule:** if overrun → trigger-phrase path slips to Day 2 morning (conversational reply is the un-cuttable core). Faking the channel is forbidden — `SEED_OFFLINE_DEMO` rows are never recorded.

## S4 — Five config dimensions, all functional
**Day 2 morning · Time limit: 4h · Depends on: S1–S3**

**User-visible value:** Every PRD configuration dimension is editable in the browser and observably changes agent behavior: scheduled wake-ups, remembered facts, skill procedures, approval pauses, enforced limits.

**Scope:** Schedules — APScheduler 3.x cron/interval jobs (workflow or run-less single-agent target) managed via API; Memory — `memory_entries` CRUD + injection; Skills — per-agent ordered procedures CRUD + injection; Interaction rules — pre-dispatch approval gate (`requires_approval` pauses run, `approval_required` event, Approve/Reject resumes/rejects); Guardrails — per-run token budget (halts with `GUARDRAIL_TRIGGERED`), runs-per-minute counter, blocked-extensions (additive mcpServers on ACP; developer-blocking agents → CLI path or `chat` mode, honestly). **Agent configuration UI (plain forms, no styling) — this is where agents become editable in the browser: a form for the six core fields (name/role/system prompt/model/tools/channels, create + edit), plus one minimum control per dimension on the agent page: memory key/value rows, a skill add/enable list, a schedule create+enable form, an approval-required toggle with Approve/Reject buttons on a paused run, and a token-budget input.**

**Acceptance criteria:** BS AC-6 (1-minute schedule fires visibly without manual action); memory edited in the UI then a reply reflects it; an agent follows its skill's steps; dev-pipeline run pauses at Deployer until Approve clicked **in the UI**; a low token budget set **in the UI** halts a run with the event visible.
**Required tests:** `test_limits` (budget + cap + rate), approval-path assertion in the e2e test.
**Demo evidence:** browser: edit a memory fact then see the next reply change; enable a skill and see it shape execution; create a 1-min schedule and watch it fire in the run view; approve a paused run; trip a guardrail.
**Scope-cut rule:** baseline is already the simplest browser-editable control per dimension (memory/skills/guardrails as JSON textareas; schedule as a single cron/interval field; approval as a toggle + two buttons). If still overrun → controls share one generic key/value+JSON editor component, but each behavior stays editable **in the browser** — never API-only. The five behaviors and the six-field form are never cut.

## S5 — Visual workflow builder (binding modify-and-run path only)
**Day 2 midday · Time limit: 2.5h · Depends on: S1–S4 APIs (agent/run/config UIs already exist from S1/S2/S4)**

**User-visible value:** A visual canvas to load a template, restructure it, and run the modified version — the PRD's "visually configurable, not hardcoded" core.

**Scope:** React Flow canvas over the nodes/edges API, **only the binding path**: **load template → modify a node → modify an edge target/condition → modify the feedback-loop max-iterations → save-as (= API duplicate) → run the modified workflow** (run + live view reuse the S2 run view). **No styling/polish pass in this slice** — default component look is acceptable; app-wide styling and error/loading/empty states are deferred to *after* the full live rehearsal succeeds (drawn from the 2.5h contingency, never from S6's mandatory work).

**Acceptance criteria:** BS AC-1 (builder edit honored by next run) and AC-2 (load → modify ≥1 node + ≥1 edge/condition → save → run modified version).
**Required tests:** `test_template_modify` (API-level modify-then-run), `test_sse_events` (one fan-out assertion).
**Demo evidence:** screen recording fragment: template loaded on canvas, a node + edge condition + loop limit edited, save-as, run honors the edits in the live run view.
**Scope-cut rule:** the binding load→modify→save-as→run path is the irreducible floor — it is never cut. Everything else (styling, extra canvas affordances) was already excluded from this slice's budget. (Agent CRUD, run view, and config controls already shipped in S1/S2/S4.)

## S6 — Mandatory release & submission work
**Day 2 evening · Time limit: 3h (mandatory, NOT contingency) · Depends on: S1–S5**
> This 3h is required submission work, not buffer. It is distinct from the separate 2.5h unallocated contingency. If S1–S5 overrun, they draw from the 2.5h contingency — never from this block, because skipping any item here means an incomplete submission.

**Mandatory items (all required):** fresh-clone `make setup && make dev` verification on a clean shell (AC-7); README completion (architecture diagram, setup, runtime tradeoff justification incl. honest OpenCode/OpenClaw treatment, language justification, add-a-template + add-a-channel instructions); integrated validation — full automated suite green (3 critical-path tests, AC-3) + `pytest -m live` opt-in real-Goose test; **run-validate the second template (Research→Analyst→Publisher) seeded in S2**; full live rehearsal (real Goose + real Telegram, builder-modification beat included); record the 8-beat demo (AC-8); repo cleanup (remove scratch, confirm `.env` gitignored, no secrets committed).

**User-visible value:** The graded deliverables: a repo a stranger can run with two commands, and the recorded proof of everything working live.

**The 8-beat recording:** create/edit agent → load + modify template → run with tool calls live → feedback loop → approval click → guardrail/token visibility → live Telegram conversation citing memory → trigger phrase run with reply.
**Acceptance criteria:** BS AC-3 (three critical-path tests green) + AC-7 (two documented commands, no interactive steps); recording includes the live Telegram conversation and the builder-modification beat; README contains all PRD-required sections.
**Required tests:** full suite green (8 files); one rehearsal pass with zero blockers before recording.
**Demo evidence:** the recording itself + README.
**Scope-cut rule:** rehearsal hour is fix-blockers-only (no new features). If rehearsal slips past its slot, record the deterministic fixture-backed path (still real runtime + real tools + live Telegram) and skip flourish beats. The recording itself is never cut — it is the deliverable.

---

## Day-1-evening cut line (pre-agreed, from readiness report)
If backend E2E (orchestrator + adapter + worker + Telegram) is not green by end of Day 1: S2 run view → poll-on-refresh (SSE wiring slips to contingency); `test_telegram_routing` → smoke assertion; all UI stays at default styling. Cuts never touch runtime integration, the live channel, the five dimensions' behavior, template modification, or the recording.

## Hours (amended — three categories)
**Feature implementation:** S1 5.5 · S2 4.0 · S3 2.5 · S4 4.0 · S5 2.5 = **18.5h**.
**Mandatory release/submission (S6):** **3.0h**.
**Genuine unallocated contingency:** **2.5h** (integration failures, overruns, and the post-rehearsal styling/polish pass if time allows).
**Total: 24.0h** over two ~12h days.

## Story → PRD traceability (one line)
S1: real runtime + agent CRUD API + plain browser read+run shell + tests(1/3) · S2: workflows/conditions/loops + A2A persistence + Dev-Pipeline template + live browser run view + tests(2,3/3) · S3: external channel live · S4: five config dimensions + interaction rules + guardrails + agent-config UI (six fields + per-dimension controls) · S5: React Flow builder (load-and-modify-and-run) · S6: single setup command + README + second-template validation + recorded demo.
