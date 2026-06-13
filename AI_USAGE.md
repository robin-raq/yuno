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
**Date:** 2026-06-13 (Units 1–6 implemented; Units 7+ not started)
**Status:** [x] In Progress  [ ] Complete  [ ] Blocked

#### AI Tools and Models Used
- Claude Sonnet 4.6 via Claude Code (ce-work skill, Units 1–2 implementation)
- Claude Opus 4.8 via Claude Code (ce-work skill, Unit 3 workflow API spine; Unit 4 message bus)
- Claude Sonnet 4.6 via Claude Code (ce-work skill, Unit 5 workflow worker/orchestrator)
- Claude Sonnet 4.6 via Claude Code (ce-work skill, Unit 6 graph traversal and next-task dispatch)

#### Important Prompts
- `/ce:work` with S2 pre-spine unit spec — scoped to parallel-safe units only (adapter hygiene + channel persistence proof) before the workflow spine begins
- `/ce:work` Unit 3 spec — workflow API spine only (GET /workflows, POST /workflows/{id}/runs, GET /runs/{id}); explicit non-goals: no worker, orchestrator, message bus, SSE, approval, or task execution. Mandated red → green → refactor.
- `/ce:work` Unit 4 spec — internal message-bus foundation only (persist A2A messages + in-process FIFO dispatch queue); explicit non-goals: no orchestrator, edge eval, feedback loop, worker execution, SSE, approval. Mandated red → green → refactor.
- `/ce:work` Unit 5 spec — minimal workflow worker/orchestrator slice: dequeue one `WorkflowDispatchItem`, resolve task, execute via existing S1 adapter path, persist task/run lifecycle events. Non-goals: graph traversal, multi-agent fan-out, SSE, approval, Goose adapter changes. Mandated red → green → refactor.
- `/ce:work` Unit 6 spec — graph traversal and next-task dispatch: evaluate outgoing edges from completed node, create next pending task, persist `task_output` handoff message, enqueue next `WorkflowDispatchItem`, keep run `running` if next task exists, complete run only at terminal node. Also fixes the Unit 4 M2 deferral: `get_run` message payload decoding and ordering. Mandated red → green → refactor.

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
- **Unit 5 — `try_dequeue()` (non-blocking) added to queue and bus**: `process_next()` must not block forever waiting for a queue item. Added `try_dequeue() → WorkflowDispatchItem | None` using `asyncio.Queue.get_nowait()` (raises `QueueEmpty` when empty). This is an additive change to `message_bus.py` that does not break existing `dequeue()` (blocking) behavior.
- **Unit 5 — adapter injected via `adapter_cls` constructor parameter**: rather than patching `AcpGooseAdapter` as a global (brittle, path-coupled), `WorkflowWorker.__init__` accepts `adapter_cls=None`, defaulting to `AcpGooseAdapter`. Tests pass `FakeAdapter` or `FailingAdapter` classes directly — no `unittest.mock.patch` needed. Production callers pass nothing and get the real adapter.
- **Unit 5 — session strategy: single `db` session for all non-streaming operations**: The commit sequence is (1) mark running + `task_started` → commit, (2) load agent + build `TaskInput`, (3) invoke adapter (mocked in unit tests), (4a success) mark completed + events → commit, (4b failure) mark failed + events → commit. The `db` session is always clean (last committed) before the adapter call, so reusing it for failure state is safe — no rollback required between step 1 commit and step 4b writes.
- **Unit 5 — streaming `on_event` uses `AsyncSessionLocal()` per event (S1 pattern)**: The adapter calls `on_event(event)` for each tool call during execution. These use their own sessions (same as S1's `task_service` pattern) because streaming events are emitted while the adapter is running — holding the outer `db` session open across an unbounded-time `adapter.invoke()` call would pin the connection. In unit tests the adapter is mocked and never calls `on_event`, so this path is only exercised live.
- **Unit 5 — M2 deferred (still latent)**: `workflow_service.get_run` reads `agent_messages` without `rowid` tiebreak (different from `MessageBusService.list_messages`). Unit 5 does not wire `deliver` into the worker (the task output is stored in `agent_tasks.output`, not as an `agent_messages` row), so `get_run` still returns `messages: []` — M2 remains latent. Fix deferred to the unit that delivers A2A messages through runs.
- **Unit 5 — single-node workflow only**: `process_dispatch_item` marks the run `completed` after one task succeeds. This is correct for the minimal case (the seeded test workflow has one start node). Multi-node edge traversal (pick the next node, enqueue the next task) is deferred to the orchestrator unit.
- **Unit 6 — two independent error domains in `process_dispatch_item`**: The original `_record_success` was monolithic. Unit 6 splits task completion from run finalization so graph traversal failure does not corrupt the task status. Domain 1 (adapter errors) routes through `_record_failure` (task+run failed). Domain 2 (graph errors) routes through `_record_run_failed_post_completion` (task stays completed; only run fails). This separation is impossible with a single try/except spanning both stages.
- **Unit 6 — `advance_after_task_completion` atomicity**: The next `agent_tasks` INSERT and the `agent_messages` INSERT (via `bus.persist_message`) are committed in a single transaction. `persist_message` is called after the INSERT but before commit — the same session sees the uncommitted next-task row when validating `to_task_id` (SQLAlchemy StaticPool single-connection semantics). The `enqueue_task` call only runs after `persist_message` returns successfully, preserving the Unit 4 persist-before-enqueue contract.
- **Unit 6 — `_record_task_completed` commits before graph advancement**: task completion is committed independently of graph traversal so that a graph failure cannot roll back the task's `completed` status. This means `_record_run_completed` and `_record_run_failed_post_completion` both start from a clean, committed state.
- **Unit 6 — Unit 4 M2 deferral resolved**: `workflow_service.get_run` now orders `agent_messages` by `created_at, rowid` (matching `MessageBusService.list_messages`) and decodes `payload` from JSON string to dict. No shared helper extracted (the two callers have slightly different projection needs); duplication is two lines.
- **Unit 6 — `edge_matches` as a pure function in `workflow_graph.py`**: extracting the condition-matching logic as a standalone function makes it unit-testable without any DB or session dependency. `always` (case-insensitive) always matches; all other conditions are case-insensitive substring matches against `task_output`. `None` output only matches `always`.
- **Unit 6 — fan-out, loop cap, no-matching-edge failure, stale dispatch deliberately deferred**: Unit 6 takes only the first matched edge (linear traversal). Fan-out (all matched edges), loop cap (`max_iterations`), `no_matching_edge` failure for non-end nodes, terminal-state guards, and stale dispatch are all deferred to later units per the spec.

#### TDD Evidence (Unit 6)
- **Failing test written first:** `backend/tests/test_workflow_graph_dispatch.py` (20 tests, `two_node` + `one_node` fixtures, `FakeAdapter`/`FailingAdapter`) authored before `workflow_graph.py` existed.
- **Failure observed:** `pytest tests/test_workflow_graph_dispatch.py -q` → **collection error** `ModuleNotFoundError: No module named 'app.services.workflow_graph'`.
- **Implementation done:** added `app/services/workflow_graph.py` (`edge_matches`, `find_next_edges`, `advance_after_task_completion`); modified `workflow_worker.py` (split `_record_success` into `_record_task_completed`/`_record_run_completed`/`_record_run_failed_post_completion`, added `advance_after_task_completion` integration); modified `workflow_service.py` (added `rowid` tiebreak + JSON payload decode in `get_run`).
- **Targeted test passed:** `pytest tests/test_workflow_graph_dispatch.py -v` → **20 passed**.
- **Full suite passed:** `pytest tests/ -q` → **71 passed, 1 skipped**.
- **S1 regression:** `pytest tests/test_agent_create.py tests/test_adapter.py -q` → **20 passed, 1 skipped**.
- **Unit 3+4+5 regression:** `pytest tests/test_workflow_api.py tests/test_message_bus.py tests/test_workflow_worker.py -q` → **31 passed**.

#### TDD Evidence (Unit 5)
- **Failing test written first:** `backend/tests/test_workflow_worker.py` (13 tests + `seed` fixture + fake adapter classes) authored before `workflow_worker.py` or `try_dequeue()` existed.
- **Failure observed:** `pytest tests/test_workflow_worker.py -q` → **collection error** `ModuleNotFoundError: No module named 'app.services.workflow_worker'`.
- **Implementation done:** added `app/services/workflow_worker.py` (`WorkflowWorker` with `process_next`/`process_dispatch_item`); added `try_dequeue()` to `InMemoryWorkflowQueue` and `MessageBusService` in `message_bus.py`.
- **Targeted test passed:** `pytest tests/test_workflow_worker.py -v` → **13 passed** (one in-flight fix: `test_start_run_does_not_auto_execute` asserted `200` but the endpoint returns `201` — corrected the test expectation before any re-run).
- **Full suite passed:** `pytest tests/ -q` → **48 passed, 1 skipped**.
- **S1 regression:** `pytest tests/test_agent_create.py tests/test_adapter.py -q` → **20 passed, 1 skipped**.
- **Unit 3+4 regression:** `pytest tests/test_workflow_api.py tests/test_message_bus.py -q` → **15 passed**.
- **Post-review (targeted review fixes B1/B2/B3 + M1/M2):** 3 new regression tests added (missing-agent, adapter-timeout, failure-handler-write-failure). `pytest tests/test_workflow_worker.py -v` → **16 passed**; full suite **51 passed, 1 skipped**; S1 **20 passed, 1 skipped**; Unit 3+4 **15 passed**. See the Review Follow-up (Unit 5) block for the TDD detail on each fix.

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
# Unit 5 RED:  pytest tests/test_workflow_worker.py -q -> collection error (module absent)
# Unit 5 GREEN: pytest tests/test_workflow_worker.py -v -> 13 passed
# Unit 5 full suite: pytest tests/ -q -> 48 passed, 1 skipped
# Unit 5 S1 regression: pytest tests/test_agent_create.py tests/test_adapter.py -q -> 20 passed, 1 skipped
# Unit 5 Unit3+4 regression: pytest tests/test_workflow_api.py tests/test_message_bus.py -q -> 15 passed
# Unit 5 post-review (B1/B2/B3 + M1/M2): pytest tests/test_workflow_worker.py -v -> 16 passed
# Unit 5 post-review full suite: pytest tests/ -q -> 51 passed, 1 skipped
# Unit 6 RED:  pytest tests/test_workflow_graph_dispatch.py -q -> collection error (module absent)
# Unit 6 GREEN: pytest tests/test_workflow_graph_dispatch.py -v -> 20 passed
# Unit 6 full suite: pytest tests/ -q -> 71 passed, 1 skipped
# Unit 6 S1 regression: pytest tests/test_agent_create.py tests/test_adapter.py -q -> 20 passed, 1 skipped
# Unit 6 Unit3+4+5 regression: pytest tests/test_workflow_api.py tests/test_message_bus.py tests/test_workflow_worker.py -q -> 31 passed
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
- [x] Unit 5: confirmed `AcpGooseAdapter` and ACP lifecycle untouched — no adapter file changed, smoke gate not required
- [x] Unit 5: confirmed `start_run` does not auto-execute (`test_start_run_does_not_auto_execute` — run created, task stays `pending`, queue stays empty)
- [x] Unit 5: confirmed Unit 3+4 behavior preserved — `test_bus_persist_message_still_works` (bus independent of worker); 15 passed on workflow_api + message_bus regression
- [x] Unit 5: confirmed `db` session reusable after failure path (`test_failure_session_remains_usable`)
- [x] Unit 5: confirmed no secrets in changed files; no SSE/approval/graph-traversal scope creep
- [x] Unit 6: confirmed `AcpGooseAdapter` and ACP lifecycle untouched — no adapter file changed, smoke gate not required
- [x] Unit 6: confirmed `start_run` does not auto-execute (`test_start_run_does_not_auto_execute_two_node` — run created, first task pending, no second task, queue empty)
- [x] Unit 6: confirmed Unit 3+4+5 behavior preserved — 31 passed on workflow_api + message_bus + workflow_worker regression
- [x] Unit 6: confirmed no SSE/approval/fan-out/loop-cap/background-worker scope creep
- [x] Unit 6: confirmed `get_run` message payload now decoded as dict, ordering deterministic (Unit 4 M2 deferral resolved)

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

**Unit 5 — TDD followed:** 13 tests written and run-to-failure (`ModuleNotFoundError`) before `workflow_worker.py` existed. One self-caught item during authoring: `test_start_run_does_not_auto_execute` asserted `status_code == 200` but the endpoint returns `201 Created` — corrected in the test file before the GREEN re-run (the implementation was not changed). No spec deviations.

**Unit 6 — TDD followed:** 20 tests (two fixtures: `two_node` and `one_node`, with `FakeAdapter`/`FailingAdapter`) authored and confirmed-failing before `workflow_graph.py` existed. Failure mode was a collection error (`ModuleNotFoundError: No module named 'app.services.workflow_graph'`) — the most definitive RED signal, proving the test file imports the module that does not yet exist. No spec deviations. The Unit 4 M2 deferral (message payload shape + ordering in `get_run`) was resolved as part of this unit and is proven by `test_get_run_messages_decoded_as_dict`.

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

#### Review Tier Decision (Unit 5)
- **Classification: high-risk-unit-closeout.** Unit 5 touches worker/orchestrator behavior, async-adjacent queue consumption, task state machine, workflow run state machine, and the live adapter execution path. This is the highest-risk tier below phase closeout.
- **Minimum review: targeted correctness review or `ce-code-review` required before commit.** Full `ce-adversarial-reviewer` not required unless the ACP adapter, auth, or external integrations change (none changed here). The adapter is mocked in all unit tests; the live execution path (`on_event` with `AsyncSessionLocal()`) is only exercised by live tests.
- **Review waiver:** not waived. A targeted correctness review must be run and recorded before committing this unit.

#### `/ce-compound` Decision (Unit 5)
- **Defer to S2 phase closeout.** Unit 5 adds the third reusable nugget in the growing workflow-spine learning set: the session-commit-per-step strategy (commit before adapter call → clean session available for failure recovery), and constructor-injection as an alternative to patching for adapter tests. These belong with the Units 3–4 nuggets in one coherent `docs/solutions/workflow-issues/` entry at S2 closeout. No `docs/solutions/` file created this unit.

#### Review Tier Decision (Unit 6)
- **Classification: high-risk-unit-closeout.** Unit 6 touches workflow graph traversal, next-task creation (new DB row), A2A message handoff (new `agent_messages` row), queue dispatch, and run state advancement. Multiple state-machine transitions happen in a single orchestrated sequence with a commit boundary in the middle. This is the same risk tier as Unit 5.
- **Minimum review: targeted correctness review required before commit.** Full `ce-adversarial-reviewer` not required: the ACP adapter, auth, and external integrations are untouched. No waiver: review must be run and recorded.
- **Review run:** targeted correctness review (classified `high-risk-unit-closeout`). The two-error-domain split (`_record_task_completed` + `_record_run_failed_post_completion`) and the atomic next-task + message commit are the highest-risk surfaces. The session-before-commit ordering and the enqueue-after-commit sequencing are tested directly.
- **Verdict: approve with minor findings.** No blocking findings. The two-domain error separation, atomic transaction boundary, and persist-before-enqueue contract are correctly implemented and test-proven. The Unit 4 M2 deferral is resolved (two-line fix, no shared helper needed at this scale). Deferred items are clearly documented and non-blocking.

#### `/ce-compound` Decision (Unit 6)
- **Defer to S2 phase closeout.** Unit 6 adds the fourth nugget: the two-error-domain pattern (commit task before graph traversal; isolate run-failure write on its own fresh session) is a generalizable pattern for any multi-stage orchestration where step N must not corrupt step N−1's committed state. This belongs with Units 3–5 in one coherent `docs/solutions/workflow-issues/` entry capturing the full workflow-spine learning set. No `docs/solutions/` file created this unit.

#### Review Follow-up (Unit 5) — Review run + findings resolved
- **Review run:** targeted multi-persona correctness review (`/code-review`, report-only) with 5 reviewers — correctness, testing, maintainability, reliability, adversarial. **Verdict: Hold for fixes.** Three independent reviewers converged on the same stuck-in-running bug; both load-bearing claims (the BUILD_SPEC §9 L497 `asyncio.wait_for` mandate and the S1 `task_service` "Finding #6" failure-path pattern) were verified directly against source before acting.
- **Root cause of all three blocking findings:** the worker mirrored S1's happy path but dropped S1's hard-won failure-path hardening. Fixes restore parity.
- **Resolved before commit (only `workflow_worker.py` + `test_workflow_worker.py` touched):**
  - **B1 (P1) — context assembly stuck-in-running** — `get_agent` + `assemble_context_preamble` + `TaskInput` build now run INSIDE the failure-handled try (previously after the step-1 `running` commit but outside the try, so a deleted agent raised `ValueError` uncaught and left task+run frozen in `running` with no terminal event). New test `test_missing_agent_fails_task_and_run`: deletes the agent before pickup, asserts task=failed, run=failed, `task_failed`+`workflow_failed` events, nothing left running.
  - **B2 (P1) — missing worker-level timeout** — `adapter.invoke` is now wrapped in `asyncio.wait_for(..., timeout=task_input.timeout_seconds)` per §9 L497/L668 (S1 `task_service.py:80-83` does the same; the worker had dropped it). A `TimeoutError` routes through the failure handler. New test `test_adapter_timeout_fails_without_hanging`: `HangingAdapter` (sleeps 30s) + config `timeout_seconds=0` → task/run failed, `workflow_failed` emitted, the call returns well under the 30s sleep.
  - **B3 (P1) — failure handler hardened** — the `except` now delegates to `_record_failure`, which (a) resets the outer session (`db.rollback()`) so a context-assembly read can't leave the shared StaticPool connection mid-transaction, (b) writes the failure on a FRESH `AsyncSessionLocal()` session in its own try/except (mirrors S1 "Finding #6"), (c) sets the failed task's `output=str(exc)`, and (d) on inner-write failure logs `"task/run may be stuck in 'running'"` and re-raises rather than swallowing. New test `test_failure_handler_write_failure_is_surfaced`: patches `AsyncSessionLocal` to raise on enter, asserts the worker re-raises AND logs the stuck-running warning (light patch, not invasive mocking, per scope).
  - **M1 (P2) — misleading event-ordering test** — `test_success_events_persisted` now orders by `text("rowid")` (SQLite insertion order) instead of the random UUID `id`, and asserts the explicit sequence `task_started < task_completed < workflow_completed`. `test_failure_events_persisted` gains the matching `task_started < task_failed < workflow_failed` assertion.
  - **M2 (P2) — prove adapter invoked exactly once** — `FakeAdapter` gains an `invoke_count`; `test_adapter_invoked_exactly_once_with_task_input` asserts `invoke_count == 1` (previously only `is not None`, which proved at-least-once). Dead `CapturingWorker` class removed.
- **Optional consistency fixes applied (same code, no scope expansion):**
  - Module docstring now states the **at-most-once, in-memory** dispatch semantics and that retry/requeue/idempotency/stale-dispatch/multi-task-run handling are deferred.
  - `task_failed` event payload now includes `agent_id` (consistent with `task_started`/`task_completed`).
  - Five duplicated `execution_events` inserts collapsed into one `_emit(...)` helper (run-level events omit `task_id`/`agent_id` explicitly); `process_dispatch_item` split into `_mark_running`/`_record_success`/`_record_failure`; `adapter_cls` annotated.
- **`message_bus.py` not modified** for these fixes — the review-driven changes were contained to the worker and its tests.
- **Validation after fixes:** `pytest tests/test_workflow_worker.py -v` → **16 passed**; `pytest tests/ -q` → **51 passed, 1 skipped**; `pytest tests/test_agent_create.py tests/test_adapter.py -q` → **20 passed, 1 skipped**; `pytest tests/test_workflow_api.py tests/test_message_bus.py -q` → **15 passed**; `make ai-usage-check PHASE=S2_UNIT_5` → PASS.
- **Deferred (recorded, non-blocking) — confirmed out of Unit 5 scope:** full idempotency machinery, duplicate-dispatch handling, stale-dispatch protection, terminal-state `WHERE status` guards, multi-task run-status precedence (failed-beats-completed), graph traversal, retry/requeue, queue back-pressure. Per BUILD_SPEC §11/§580 these are explicitly deferred; revisit at the orchestrator unit. The at-most-once delivery choice is now documented in the module docstring.
- **`/ce-compound`:** deferred to S2 phase closeout (see decision above).
- **Local phase-closeout review-gate false-positive (deferred — local tooling):** `.local/phase_closeout.py` matched review-*recommendation* keywords as review *completion*, reporting the gate `SATISFIED` before the review actually ran. The gitignored `.local/` tool has no effect on the committed repo; the human review (this block) is the real gate. Fix deferred as a `.local/` tooling improvement — require a distinct "Review Follow-up — Review run" marker rather than matching recommendation prose.

#### Process Friction Note (for later Stage-2 automation)
- Per-unit closeout (update AI_USAGE across ~8 subsections + run `phase-status`/`commit-plan`/`ai-usage-check` by hand) is repetitive across Units 3–4. This is exactly what the planned `make phase-closeout` (Stage 2, with the review-decision gate) is meant to compress into one command. Friction logged here so the eventual automation targets the real pain: the multi-section AI_USAGE edit + the three read-only checks, run together, classified, with the review-gate status surfaced.

#### Deferred or Blocked Work
- **`mcpServers` wiring**: Deferred to S4+ (per-agent MCP server configs not in schema yet)
- **Channel persistence**: Deferred to S3 (real channel_id comes from Telegram bot setup)
- **Unit 3 graph validation**: Only minimal blocking checks implemented (workflow exists, ≥1 start node, start node's agent exists). **Deferred** per §6: orphan-node detection (node connected to no edges), full edge-target validation, and multiple-start-node fan-out handling. Documented here as required by the spec.
- **Unit 3 execution path**: enqueue of the start message, worker loop, orchestrator/edge evaluation, message bus, SSE endpoint (`/events`), replay (`/runs/{id}/events`), and approval endpoints — all deferred to later S2 units. Run stays `pending`; task stays `pending`.
- **Unit 4 — wiring + worker**: the message bus is built but unused — `start_run` does not yet `deliver`, and nothing drains the queue. Worker loop, orchestrator edge traversal, feedback-loop cap, dispatch-item task validation, queue back-pressure handling (`put` blocks at maxsize=1000), and SSE remain deferred to Units 5–6.
- **Unit 5 — M2 (RESOLVED in Unit 6):** `workflow_service.get_run` now orders `agent_messages` by `created_at, rowid` (matching `MessageBusService.list_messages`) and decodes `payload` from JSON string to dict. Fixed as part of Unit 6 since messages now flow through `GET /runs/{run_id}`. Proven by `test_get_run_messages_decoded_as_dict`.
- **Unit 5 — multi-node graph traversal:** addressed in Unit 6 (linear single-next-node only). Fan-out, loop cap, and non-"always" edge guards deferred to Units 7+.
- **Unit 5 — SSE event streaming:** no SSE emitted. All events are persisted in `execution_events` only. SSE delivery deferred to the events endpoint unit.
- **Unit 5 — feedback loop / approval:** feedback iteration cap and approval endpoints not started; deferred to Units 7+.
- **Unit 6 — fan-out (multiple matched edges):** only the first matched edge is taken (linear traversal). Fan-out to all matched edges deferred.
- **Unit 6 — loop cap (`max_iterations`):** no cycle detection or feedback-loop cap. Deferred.
- **Unit 6 — `no_matching_edge` non-terminal failure:** a non-end node with no matched outgoing edges silently terminates the run today (treated as a terminal node). The correct behavior (run fails with `no_matching_edge`) is deferred.
- **Unit 6 — stale dispatch protection:** a duplicate `WorkflowDispatchItem` for an already-completed task would re-enter `process_dispatch_item`. No terminal-state guard blocks it today. Deferred.
- **Units 7+**: SSE endpoint (`/events`), replay (`/runs/{id}/events`), approval endpoints, run view — not started.

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
