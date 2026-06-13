# AI Usage Log — Project Yuno

This file records AI tool usage for every feature-bearing story. A story is **not complete** until its entry here is filled in. Copy the template below for each story and remove the placeholder comment.

---

## Template

```
### Story: S[N] — [Title]
**Date:** YYYY-MM-DD
**Status:** [ ] In Progress  [ ] Complete  [ ] Blocked

#### AI Tools and Models Used
- Tool/model: [e.g. Claude Opus 4.8 via Claude Code]
- Tool/model: [e.g. Claude Sonnet 4.6 for code review pass]

#### Important Prompts
- [Summarize any prompt that materially shaped an implementation decision]
- [Include prompts that produced non-obvious or reviewable outputs]

#### Decisions Made with AI Assistance
- [Decision + brief rationale — e.g. "Used asyncio.wait_for rather than a manual timeout flag because the adapter ABC has no cancellation hook"]
- [Flag any decision that deviates from BUILD_SPEC.md or SYSTEM_DESIGN.md]

#### Validation Commands Run
```bash
# Paste actual commands and abbreviated output
pytest test_<file>.py -v
make smoke-goose
make setup && make dev
```

#### Manual Review Performed
- [ ] Reviewed diff for scope creep beyond story bounds
- [ ] Verified no secrets in staged files
- [ ] Checked that BUILD_SPEC.md contracts were followed (not just "it works")
- [ ] Ran the story's required tests and confirmed they pass

#### Review Findings or Mistakes Caught
- [List any bugs, incorrect assumptions, or spec deviations found during review]
- [Include findings caught by AI review agents as well as manual review]
- "None" is a valid entry if the review was clean

#### Deferred or Blocked Work
- [Anything that hit the scope-cut rule — state what was deferred and where it lands]
- [Any blocking issue that was not resolved — include the decision made]

#### Architectural or Specification Amendments
- [Any change to SYSTEM_DESIGN.md or BUILD_SPEC.md triggered by implementation findings]
- [If none: "No amendments made"]
- All amendments must also be recorded in DECISION_LOG.md

#### Final Completion Status
- [ ] All story acceptance criteria satisfied (cite BUILD_SPEC.md section)
- [ ] Required tests green (default pytest run)
- [ ] Manual demo evidence captured
- [ ] Commit made following commits.md conventions
- [ ] AI_USAGE.md updated (this entry)
```

---

## Entries

### Story: S1 — Verified runtime spine
**Date:** 2026-06-12 (implementation) · 2026-06-13 (ACP protocol fixes + closeout)
**Status:** [ ] In Progress  [x] Complete

#### AI Tools and Models Used
- Claude Sonnet 4.6 via Claude Code (primary implementation, all files)
- ce-adversarial-reviewer (compound-engineering plugin) — post-implementation review pass (18 findings)
- Cursor agent — ACP protocol drift fixes, smoke gate unblock, formal S1 closeout review, closeout cleanup

#### Important Prompts
- `/ce:work` with the full S1 spec — initiated all implementation with frozen source hierarchy (project_yuno.pdf → goose-spike-report.md → SYSTEM_DESIGN.md → BUILD_SPEC.md → stories.md)
- Adversarial review prompt produced 18 findings (3 Blocking, 7 High, 6 Medium, 2 Low); all Blocking and High findings fixed in current code
- Key prompt constraint: "Do not begin S2" and "Hard gate: run smoke gate before application implementation"
- Formal S1 closeout review (2026-06-13) — read-only verification after ACP protocol fixes; no full `ce-code-review` or human PR review occurred before this closeout review

#### Decisions Made with AI Assistance
- **Goose ACP lifecycle (current, superseding earlier narrative)**: Goose 1.37.0 uses synchronous `initialize` POST; `acp-connection-id` comes from the response header (not from opening GET SSE first). `session/new` runs on a connection-level SSE stream with `Acp-Connection-Id`. `session/prompt` runs on a separate session-scoped SSE stream (separate httpx client) with both `Acp-Connection-Id` and `Acp-Session-Id`. Prompt params: `{sessionId, prompt: [{type: "text", text: "..."}]}`. Events nest under `params.update.sessionUpdate` (string discriminator) with legacy-shape fallback.
- **Superseded decision (2026-06-12 adversarial fix)**: The original "single outer SSE context for the entire invoke call" narrative is outdated — it addressed Blocking #1–2 against the June spike protocol, but was replaced after live re-probe showed protocol drift. Intent (reliable conn lifecycle + id-correlated RPC) is preserved via the current flow above.
- **itertools.count(1) for RPC IDs**: Chosen over `self._rpc_id += 1` because it avoids the non-atomic read-increment-write pattern in a shared counter (though single-threaded asyncio makes both safe, `count()` is idiomatic and self-documenting).
- **Fresh AsyncSession per event in persist_event**: Avoids corrupt outer session transaction state from intermediate commits. Alternative: `db.begin_nested()` (savepoints) — rejected as more complex with aiosqlite.
- **SQLAlchemy Core (not ORM)**: Follows BUILD_SPEC §5.1 — `metadata.create_all()` replaces Alembic for S1, no migration history needed.
- **`##` sanitization via line-indent**: Prevents LLM context injection from user-controlled memory/skill values (memory + skill steps only; `system_prompt` not sanitized). Alternative: strip `#` characters entirely — rejected as too aggressive for markdown content.
- **`useRef` double-submit guard**: React `useState` is async; `useRef` provides a synchronous sentinel that blocks a second submit before the first re-render disables the button.

#### Validation Commands Run
```bash
# Closeout validation (2026-06-13):
cd backend && python3 -m pytest tests/ -q
# Result: 16 passed, 1 skipped (live)

make smoke-goose
# Result (closeout 2026-06-13): PASSED — 3 tool_call events, artifact verified, frames saved
# Note: first attempt failed when port 3284 was occupied; succeeded after clearing port

# TypeScript check (from frontend/):
npx tsc --noEmit
# Result: 0 errors (initial implementation pass)
```

#### Manual Review Performed
- [x] Reviewed diff for scope creep beyond story bounds
- [x] Verified no secrets in staged files (only .env.example with placeholder values)
- [x] Checked that BUILD_SPEC.md contracts were followed (nullable run_id/node_id, all 14 tables, six PRD fields on create API)
- [x] Ran the story's required tests and confirmed they pass (16/16 non-live, 1 live skipped)
- [x] Formal S1 closeout review run (2026-06-13) — verified Blocking/High fixes in current code; assessed ACP protocol drift fixes
- [ ] Full `ce-code-review` or human PR review — not performed before closeout review

#### Review Findings or Mistakes Caught

**Blocking findings fixed (adversarial review, 2026-06-12):**
1. `acp_goose.py`: Connection-level SSE lifecycle unreliable — **fixed** (current: sync `initialize` POST + scoped conn SSE for `session/new` only; superseded original single-stream fix narrative).
2. `acp_goose.py`: Competing second SSE connection — **fixed** (eliminated `_new_session`; separate session client for prompt).
3. `acp_goose.py`: JSON-RPC id not correlated — **fixed** (`data.get("id") == session_rpc_id` / `prompt_id`).

**High findings fixed:**
4. `task_service.py`: `persist_event` shared outer session — **fixed** (fresh `AsyncSessionLocal()` per event).
5. `task_service.py`: Failure handler could leave task stuck in `running` — **fixed** (separate `fail_db`; edge case if fail_db also fails).
6. `acp_goose.py`: Session not closed on error — **fixed** (`try/finally` + `_close_session`).
7. `agent_service.py`: Preamble injection via memory/skills — **partially fixed** (`_sanitize_user_content()` on memory + skill steps; `system_prompt` not sanitized).
8. `test_adapter.py`: Vacuous adapter test — **fixed** (`test_adapter_invoke_routes_events` calls `adapter.invoke` with mocks).

**Medium findings fixed:**
9. `conftest.py`: DB tables not reset between tests — **fixed** (`drop_all + create_all` per test).
10. `smoke_gate.py`: `time.sleep()` in async coroutine — **fixed** (`await asyncio.sleep()`).
11. `App.tsx`: Double-submit race — **fixed** (`useRef` sentinel).

**Formal closeout review (2026-06-13) — deferred / open items:**
- No ACP retry on transient errors
- Structured logging deferred
- Copy-to-clipboard deferred
- `agent_config.extensions` stored as JSON string (Info)
- Live `tool_call` frames show `tool: "unknown"` (new ACP event field mapping gap)
- `TaskInput.extensions` not wired to `session/new mcpServers` (server `--with-builtin developer` covers S1)
- `channels` accepted in create API but not persisted to `channel_connections`
- Frame replay test not implemented (`test_adapter.py` checks frames exist; BUILD_SPEC names `test_acp_adapter.py`)
- `session/prompt` POST ordering — mitigated (SSE opened before POST)
- Partial `agent_message_chunk` assembly — works in practice via smoke gate output

#### Deferred or Blocked Work
- **Smoke gate (AC-4)**: Passed 2026-06-13 — 3 `tool_call` events captured, artifact verified, frames saved to `data/smoke/frames.json` (local; gitignored).
- **ACP protocol update (2026-06-13)**: Documented in Decisions section above; adapter + tests updated.
- **Second template execution** (S2): Explicitly out of scope for S1.
- **Live SSE browser streaming**: Deferred beyond S1 — task API returns full result synchronously.
- **Workflow orchestrator / message bus / run SSE**: S2 scope — not started.

#### Architectural or Specification Amendments
- No amendments to BUILD_SPEC.md or SYSTEM_DESIGN.md were required.
- Implementation confirmed that `agent_tasks.run_id` and `node_id` must be NULLABLE (standalone tasks have neither) — already specified in BUILD_SPEC §5.2.
- Session-scoped SSE and POST require both `Acp-Connection-Id` and `Acp-Session-Id` headers (verified against Goose 1.37.0 live behavior).

#### S1 Acceptance Criteria Mapping (BUILD_SPEC / stories.md)
S1 does **not** complete AC-1 through AC-7. S1 delivers:
- **AC-4** (real-runtime smoke gate): `make smoke-goose` with real `tool_call` + on-disk artifact
- **Partial AC-3**: `test_agent_create.py` + `test_adapter.py` (not full three critical-path suite — `test_workflow_run_e2e.py` and `test_message_delivery.py` are S2)
- **Runtime spine**: Agent CRUD API (six fields on create), single-agent task execution, persisted `execution_events`, plain browser runner
- **Schema/seed foundation**: 14 tables via `create_all`, 6 agents + 2 workflow templates seeded (templates not run-validated in S1)
- **AC-7** (`make setup && make dev`): implemented but fresh-clone verification deferred to S6

#### Final Completion Status
- [x] S1 story scope implemented (runtime spine, agent CRUD, task execution, browser shell, tests)
- [x] Required S1 tests green: 16 passed, 1 skipped (live)
- [x] AC-4 smoke gate passed (`make smoke-goose`, 3 tool_call events, artifact on disk)
- [x] Manual browser demo evidence — stack verified 2026-06-13: `make dev` services healthy; agent list/create/delete via API; task submit returned `completed` with 3 `tool_call` events + `task_completed`; Vite proxy to `/agents` returned 200. Visual browser session not recorded in this closeout session (API + proxy path confirms browser shell wiring).
- [x] Commit — 10 single-responsibility commits on `main` (2026-06-13)
- [x] AI_USAGE.md updated (this entry)

---

### Story: S2 — Multi-agent workflow with persisted A2A messaging
**Date:** 2026-06-13 (Units 1–4 implemented; Units 5+ not started)
**Status:** [x] In Progress  [ ] Complete  [ ] Blocked

#### AI Tools and Models Used
- Claude Sonnet 4.6 via Claude Code (ce-work skill, Units 1–2 implementation)
- Claude Opus 4.8 via Claude Code (ce-work skill, Unit 3 workflow API spine; Unit 4 message bus)

#### Important Prompts
- `/ce:work` with S2 pre-spine unit spec — scoped to parallel-safe units only (adapter hygiene + channel persistence proof) before the workflow spine begins
- `/ce:work` Unit 3 spec — workflow API spine only (GET /workflows, POST /workflows/{id}/runs, GET /runs/{id}); explicit non-goals: no worker, orchestrator, message bus, SSE, approval, or task execution. Mandated red → green → refactor.
- `/ce:work` Unit 4 spec — internal message-bus foundation only (persist A2A messages + in-process FIFO dispatch queue); explicit non-goals: no orchestrator, edge eval, feedback loop, worker execution, SSE, approval. Mandated red → green → refactor.

#### Decisions Made with AI Assistance
- **Unit 1 — `_resolve_tool_name` extracted as named helper**: The inline `update.get("toolName", update.get("tool", "unknown"))` was correct but silent on degradation. Extracted to `_resolve_tool_name(update) -> str` with a `log.warning` when the name falls through to `"unknown"`. This converts a silent observability gap into a logged event.
- **Unit 1 — `mcpServers: []` comment**: Goose builtins (e.g. "developer") are loaded at server startup via `--with-builtin developer` (Makefile). The `mcpServers` array in `session/new` is for HTTP MCP servers — a different mechanism. Wiring `TaskInput.extensions` to `mcpServers` is not appropriate for S2 because extensions are startup-time and mcpServers are per-session HTTP configs. Deferred to S4+ when agent schemas carry explicit MCP server configs.
- **Unit 2 — channel persistence deferred**: `AgentCreate.channels: list[str]` carries channel type names (e.g. `["telegram"]`) without `channel_id`. `channel_connections` requires `channel_id NOT NULL` — there is no valid value at agent creation time. Persisting an empty `channel_id` would be meaningless data. Decision: prove deferred with a comment in `create_agent` + a dedicated test (`test_channels_deferred_from_create_payload`) that asserts `channels: []` in the response.
- **Unit 2 — `channels` added to `get_agent` response**: `_get_channels(db, agent_id)` queries `channel_connections.channel_type` and surfaces the result on `get_agent` and (via `return await get_agent(...)`) on `create_agent`. Additive response key, backward-compatible. Returns `[]` until S3 sets up real connections.
- **Unit 3 — run status stays `pending` after POST**: BUILD_SPEC §9.1 says `start_workflow_run` creates the run row as `pending`; §10's `pending → running` transition is the worker dequeuing, which Unit 3 does not build. Setting `running` with no worker would show a permanently-stuck run. Chose `pending` (honest: created, awaiting worker).
- **Unit 3 — run `started_at` set, task `started_at` null**: The run-level `started_at` marks when `start_workflow_run` was invoked (the run was started); the task-level `started_at` is set later when the worker dequeues (§10 AgentTask). This cleanly separates "run started" from "task started" and satisfies the contract field without overclaiming execution.
- **Unit 3 — no enqueue / no message row**: §9.1 also "enqueues the start message", but no `asyncio.Queue`/worker exists yet and the spec forbids building one in this unit. Unit 3 stops after the first pending task + `workflow_started` event. No `agent_messages` row is created (messaging is a later unit).
- **Unit 3 — structured errors via `HTTPException(detail={...})`**: `workflow_not_found` (404), `graph_validation_failed` (400), `run_not_found` (404) returned as `{"detail": {"error": ..., "message": ...}}`, giving stable machine-readable codes while staying within FastAPI conventions.
- **Unit 3 — tasks ordered by SQLite `rowid`**: `agent_tasks` has no `created_at` column, so the run snapshot orders tasks by `rowid` (insertion = "created" order). Project is SQLite-only, so this is safe; trivial for the single Unit-3 task but correct as tasks accrue.
- **Unit 4 — `MessageBusService` with an injectable `InMemoryWorkflowQueue`**: rather than a module-level singleton queue (risky shared state across tests), the service takes a queue at construction. Each test builds `MessageBusService(InMemoryWorkflowQueue())`, so no cross-test leakage. The queue wraps `asyncio.Queue(maxsize=1000)` per §11.
- **Unit 4 — explicit run/task validation (FKs unenforced in SQLite)**: `persist_message` checks the referenced run and from/to tasks exist and raises `UnknownRun`/`UnknownTask` *before* insert. SQLite does not enforce these foreign keys by default, so the explicit guard is the real protection against an invalid message target silently persisting/enqueuing.
- **Unit 4 — persist-before-queue ordering (§11)**: `deliver()` calls `persist_message` (which commits) first, then `enqueue_task`. Validation/commit failure raises before the enqueue line is reached, so a failed message never produces a visible queue item. `persist_message` rolls back on failure to keep the session reusable.
- **Unit 4 — deterministic message order via ISO `created_at`**: `agent_messages.created_at` server default is `datetime('now')` (1-second granularity → collisions on quick inserts). `persist_message` stamps an explicit `datetime.now(timezone.utc).isoformat()` (µs precision); `list_messages` orders by `created_at` then `rowid`. This makes both `list_messages` and the Unit-3 `get_run` message trail deterministic without touching Unit 3 code.
- **Unit 4 — message bus is standalone, not wired into `start_run`**: the spec scopes Unit 4 to the *foundation*. `start_run` is unchanged; the worker/orchestrator (later units) will call `deliver`. Proven by `test_start_run_still_pending_with_no_dispatch` (run starts, task stays pending, injected queue stays empty).

#### TDD Evidence (Unit 4)
- **Failing test written first:** `backend/tests/test_message_bus.py` (6 tests + `bus_seed` fixture) authored before `message_bus.py` existed.
- **Failure observed:** `pytest tests/test_message_bus.py -q` → **collection error** `ModuleNotFoundError: No module named 'app.services.message_bus'`.
- **Implementation done:** added `app/services/message_bus.py` (`AgentMessageDraft`, `WorkflowDispatchItem`, `InMemoryWorkflowQueue`, `MessageBusService` with `persist_message`/`enqueue_task`/`deliver`/`dequeue`/`queue_size`/`list_messages`, `UnknownRun`/`UnknownTask`).
- **Targeted test passed:** `pytest tests/test_message_bus.py -q` → **6 passed**.
- **Full suite passed:** `pytest tests/ -q` → **33 passed, 1 skipped** (was 26/27 + 1).

#### TDD Evidence (Unit 3)
- **Failing test written first:** `backend/tests/test_workflow_api.py` (6 tests + `seeded_workflows` fixture) authored before any implementation.
- **Failure observed:** `pytest tests/test_workflow_api.py -q` → **6 failed** (endpoints absent: `KeyError: 'run_id'`, `TypeError: string indices` on the string error detail, empty list for GET /workflows). Fixture seeded cleanly, proving the shared-session seeding approach before code existed.
- **Implementation done:** added `app/services/workflow_service.py` + `app/api/workflows.py`, registered the router in `app/main.py`.
- **Targeted test passed:** `pytest tests/test_workflow_api.py -q` → **6 passed**.
- **Full suite passed:** `pytest tests/ -q` → **26 passed, 1 skipped** (was 20 + 1).

#### Validation Commands Run
```bash
cd backend && python3 -m pytest tests/ -q
# Units 1–2: 20 passed, 1 skipped (4 new tests)
# Unit 3 RED:  pytest tests/test_workflow_api.py -q  -> 6 failed (endpoints absent)
# Unit 3 GREEN: pytest tests/test_workflow_api.py -q -> 6 passed
# Unit 3 review follow-up: 7 workflow tests; full suite 27 passed, 1 skipped
# Unit 4 RED:  pytest tests/test_message_bus.py -q   -> collection error (module absent)
# Unit 4 GREEN: pytest tests/test_message_bus.py -q  -> 6 passed
# Unit 4 review follow-up: 8 message-bus tests (+M1 commit-failure, +L1 from_task); full suite 35 passed, 1 skipped
```

#### Manual Review Performed
- [x] Reviewed diff for scope creep — no workflow orchestration, SSE, or S3 work touched
- [x] Verified no secrets in staged files
- [x] Checked BUILD_SPEC contracts — adapter lifecycle unchanged; agent CRUD response shape additive only
- [x] Ran story tests and confirmed pass
- [x] Unit 3: confirmed `AcpGooseAdapter` and ACP lifecycle untouched (no adapter file changed → smoke gate not required)
- [x] Unit 3: confirmed S1 agent/task APIs unchanged; new router additive (`/workflows`, `/runs`)
- [x] Unit 3: confirmed validation runs before any insert (invalid graph → zero rows, test-proven); inserts FK-ordered under a single commit
- [x] Unit 4: confirmed `AcpGooseAdapter`/ACP lifecycle untouched (smoke gate not required); no worker loop, no task execution, no SSE added
- [x] Unit 4: confirmed `message_bus` is standalone (not wired into `start_run`); queue is injectable (no shared singleton state across tests)
- [x] Unit 4: confirmed persist-before-queue (failure → zero queue items, test-proven) and `persist_message` rolls back on failure

#### Review Findings or Mistakes Caught

**Process finding — TDD not followed for Unit 2:**
- `_get_channels` and the `channels` key on the `get_agent` response were implemented before the failing test was written. This conflicts with the repo/global preference for test-driven or eval-first work on feature-bearing code.
- The behavior is now covered by tests:
  - `test_channels_deferred_from_create_payload`
  - updated `test_create_agent_all_six_fields` (channels assertion added)
- Current validation is green: 20 passed, 1 skipped.
- No rework required for this small slice, but Units 3+ must follow red → green → refactor.

**Forward rule — S2 Units 3+ must follow TDD:**
1. Write or update the failing test first.
2. Run the targeted test and show the failure.
3. Implement the smallest change to make it pass.
4. Run the targeted test again.
5. Run the full test suite.
6. Update `AI_USAGE.md` with the test-first evidence.

**Unit 3 — TDD followed (forward rule honored):** Tests written and run-to-failure before implementation; no rework. No spec deviations found. No mistakes caught in review beyond the deliberate scope decisions documented above.

**Unit 4 — TDD followed:** Tests written and run-to-failure (module-absent collection error) before implementation; no rework. Two self-caught items during authoring: (a) a test called `queue.queue_size()` where the queue exposes `size()` — fixed before the RED run; (b) removed a dead `_qsize_helper_exists` function from the test file (never collected, no value). No spec deviations.

#### Review Tier Decision (Unit 3)
- **Recommended: targeted review** of `workflow_service.py` + `api/workflows.py` + `test_workflow_api.py` before commit. Unit 3 touches run creation and DB persistence (run + task + event), so it clears the "always-on correctness" bar but does not touch auth, external integrations, or the proven ACP adapter — full `ce-adversarial-reviewer` / `ce-code-review` is not yet warranted for this thin, additive, well-tested slice. Escalate to `ce-code-review` once the worker/orchestrator (next unit) introduces async execution and edge evaluation.

#### Review Follow-up (Unit 3) — Review run + findings resolved
- **Review run:** targeted correctness review (classified `high-risk-lite` per the automation pacing/review-gate design). **Verdict: approve with minor fixes.** No blocking/high findings.
- **Resolved before commit:**
  - **M2** — added `test_start_run_missing_start_agent_creates_no_rows`: a start node whose `agent_id` references no agent → 400 `graph_validation_failed`, zero `workflow_runs` and zero `agent_tasks` rows. Closes the previously-untested `_validate_graph` missing-agent branch.
  - **L4** — strengthened `test_list_workflows_returns_seeded` to assert **both** `dev_pipeline` and `research_pipeline` by `template_key` (ids resolved from the response, never hardcoded).
- **Deferred (recorded, non-blocking):** M1 (S1 string-detail vs S2 structured-detail error shapes — unify at a later consistency pass, not by touching S1 now); L1 (multi-start ordering), L2 (`rowid` SQLite coupling), L3 (no catch-all 500 handler in the workflows router), L5 (empty-input edge) — all revisit with the orchestrator unit.
- **Validation after follow-up:** `pytest tests/test_workflow_api.py -q` → 7 passed; `pytest tests/ -q` → 27 passed, 1 skipped.

#### `/ce-compound` Decision (Unit 3)
- **Defer `/ce-compound` until the S2 workflow spine is further along.** Unit 3 produced one reusable nugget — the in-memory-SQLite shared-connection seeding pattern for API tests (seed through the same `db` session the client override yields) — but it is small and not yet battle-tested across units. Recommend running `/ce-compound` at S2 closeout (after the worker/orchestrator lands) to capture the workflow-spine learnings as one coherent entry rather than fragmenting them. No `docs/solutions/` file created this unit.

#### Review Tier Decision (Unit 4)
- **Classification: high-risk-lite** (DB persistence + queue semantics; no adapter/async-worker/SSE). **Recommended: targeted correctness review** of `message_bus.py` + `test_message_bus.py` before commit — same tier as Unit 3. Not full `ce-code-review`/`ce-adversarial-reviewer`: the queue is in-process and inert (no consumer yet), and persistence reuses the proven SQLAlchemy-Core + commit/rollback pattern. Escalate to `ce-code-review` at the worker unit, when something actually *drains* the queue concurrently with task execution.

#### Review Follow-up (Unit 4) — Review run + findings resolved
- **Review run:** targeted correctness review (3 independent finder agents — correctness, test-quality, concurrency/data-model — + verification against source). **Verdict: approve with minor fixes.** No blocking/high findings.
- **Resolved before commit (only `message_bus.py` + `test_message_bus.py` touched):**
  - **M1** — added `test_deliver_commit_failure_rolls_back_and_does_not_enqueue`: a CHECK-violating `msg_type="garbage"` drives a real persistence failure through `deliver()`; asserts it raises `IntegrityError`, `queue_size()==0`, zero rows persisted, and the **same session still persists a valid message afterward**. Closes the previously-uncovered `except/rollback` path and proves persist-before-queue for a true DB failure (not only pre-insert validation).
  - **L1** — added `test_deliver_unknown_from_task_raises`: an unknown `from_task_id` raises `UnknownTask`, persists nothing, enqueues nothing (the from-side validation branch, previously only covered for `to_task_id`).
  - **L3** — corrected the `created_at` comment: deterministic order comes from the `rowid` tiebreak in `list_messages`, not timestamp precision (`isoformat()` omits µs when 0).
- **Deferred (recorded, non-blocking):**
  - **M2** — `workflow_service.get_run` reads `agent_messages` with a different ordering (`created_at` only, no `rowid` tiebreak) and a different payload shape (raw JSON string vs `list_messages`' decoded dict). Latent today (`get_run` returns `messages: []` until the bus is wired into runs). **Fix at Unit 5** when messages flow through `GET /runs/{run_id}` — extract one shared `_messages_for_run` helper used by both readers. Not touched now (out of Unit 4 scope; would modify `workflow_service.py`).
  - **L2** — queue back-pressure: `asyncio.Queue.put` blocks at `maxsize=1000` with no consumer. **Deferred to the worker unit** (`put_nowait` + `QueueFull` once a drainer exists).
- **Validation after follow-up:** `pytest tests/test_message_bus.py -q` → 8 passed; `pytest tests/ -q` → 35 passed, 1 skipped.

#### `/ce-compound` Decision (Unit 4)
- **Defer again to S2 phase closeout.** Unit 4 adds a second small reusable nugget (persist-before-queue ordering + injectable-queue-over-singleton for test isolation), but it is the same theme as Unit 3's. Capture both at the S2 workflow-spine closeout as one coherent `docs/solutions/workflow-issues/` entry rather than fragmenting. No `docs/solutions/` file created this unit.

#### Process Friction Note (for later Stage-2 automation)
- Per-unit closeout (update AI_USAGE across ~8 subsections + run `phase-status`/`commit-plan`/`ai-usage-check` by hand) is repetitive across Units 3–4. This is exactly what the planned `make phase-closeout` (Stage 2, with the review-decision gate) is meant to compress into one command. Friction logged here so the eventual automation targets the real pain: the multi-section AI_USAGE edit + the three read-only checks, run together, classified, with the review-gate status surfaced.

#### Deferred or Blocked Work
- **`mcpServers` wiring**: Deferred to S4+ (per-agent MCP server configs not in schema yet)
- **Channel persistence**: Deferred to S3 (real channel_id comes from Telegram bot setup)
- **Unit 3 graph validation**: Only minimal blocking checks implemented (workflow exists, ≥1 start node, start node's agent exists). **Deferred** per §6: orphan-node detection (node connected to no edges), full edge-target validation, and multiple-start-node fan-out handling. Documented here as required by the spec.
- **Unit 3 execution path**: enqueue of the start message, worker loop, orchestrator/edge evaluation, message bus, SSE endpoint (`/events`), replay (`/runs/{id}/events`), and approval endpoints — all deferred to later S2 units. Run stays `pending`; task stays `pending`.
- **Unit 4 — wiring + worker**: the message bus is built but unused — `start_run` does not yet `deliver`, and nothing drains the queue. Worker loop, orchestrator edge traversal, feedback-loop cap, dispatch-item task validation, queue back-pressure handling (`put` blocks at maxsize=1000), and SSE remain deferred to Units 5–6.
- **Units 5+**: Orchestrator, worker execution against Goose, edge/feedback logic, SSE, approval endpoints, run view — not started; awaiting review gate per spec.

#### Architectural or Specification Amendments
- No amendments to BUILD_SPEC.md or SYSTEM_DESIGN.md required.
- Confirmed: `channel_connections.channel_id NOT NULL` with no server default makes pre-S3 persistence impossible without schema change. Architecture is correct as-is.
- Noted (no change required): BUILD_SPEC §9.1 ("creates row status=pending") vs §10 ("pending → running : start_workflow_run") is a minor internal tension; Unit 3 follows §9.1's explicit `pending` since the worker that performs the transition is out of scope.

---

### Story: S3 — Live Telegram channel
**Date:** _(fill in)_
**Status:** [ ] In Progress  [ ] Complete  [ ] Blocked

> Fill in when S3 begins.

---

### Story: S4 — Five config dimensions, all functional
**Date:** _(fill in)_
**Status:** [ ] In Progress  [ ] Complete  [ ] Blocked

> Fill in when S4 begins.

---

### Story: S5 — Visual workflow builder
**Date:** _(fill in)_
**Status:** [ ] In Progress  [ ] Complete  [ ] Blocked

> Fill in when S5 begins.

---

### Story: S6 — Mandatory release and submission work
**Date:** _(fill in)_
**Status:** [ ] In Progress  [ ] Complete  [ ] Blocked

> Fill in when S6 begins.
