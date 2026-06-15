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
- Claude Opus 4.8 via Claude Code (ce-work skill, Unit 7 graph-execution semantics: loop cap, no_matching_edge, branch selection)
- ce-correctness-reviewer (compound-engineering) — Unit 7 targeted correctness review (Approve to commit; 2 medium, 2 low, no blocking/high)

#### Important Prompts
- `/ce:work` with S2 pre-spine unit spec — scoped to parallel-safe units only (adapter hygiene + channel persistence proof) before the workflow spine begins
- `/ce:work` Unit 3 spec — workflow API spine only (GET /workflows, POST /workflows/{id}/runs, GET /runs/{id}); explicit non-goals: no worker, orchestrator, message bus, SSE, approval, or task execution. Mandated red → green → refactor.
- `/ce:work` Unit 4 spec — internal message-bus foundation only (persist A2A messages + in-process FIFO dispatch queue); explicit non-goals: no orchestrator, edge eval, feedback loop, worker execution, SSE, approval. Mandated red → green → refactor.
- `/ce:work` Unit 5 spec — minimal workflow worker/orchestrator slice: dequeue one `WorkflowDispatchItem`, resolve task, execute via existing S1 adapter path, persist task/run lifecycle events. Non-goals: graph traversal, multi-agent fan-out, SSE, approval, Goose adapter changes. Mandated red → green → refactor.
- `/ce:work` Unit 6 spec — graph traversal and next-task dispatch: evaluate outgoing edges from completed node, create next pending task, persist `task_output` handoff message, enqueue next `WorkflowDispatchItem`, keep run `running` if next task exists, complete run only at terminal node. Also fixes the Unit 4 M2 deferral: `get_run` message payload decoding and ordering. Mandated red → green → refactor.
- `/ce:work` Unit 7 spec — graph-execution semantics: feedback-loop cap (§9.3), `no_matching_edge` failure on non-end nodes (§9.5), and correct conditional branch selection across all outgoing edges (§9.2). Authored after a sequencing analysis showed the seed templates (dev_pipeline, research_pipeline) contain conditional loop edges with `max_iterations=2` that Unit 6's uncapped first-match traversal would infinite-loop on. Explicit non-goals: SSE, replay, approval, true fan-out, retries, background loop. Mandated red → green → refactor.

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
- **Unit 7 — loop-edge predicate is `condition != "always"` AND `to_node already executed in this run`**: §9.3 defines a loop edge purely structurally ("points to an already-executed node"), but in a 2-cycle (Coder⇄Reviewer) the forward "always" edge also points to an executed node once the cycle is entered — a naive structural check would cap the forward edge and miscount iterations. Adding the non-"always" guard isolates feedback (conditional) from forward progression (unconditional), landing exactly on the §9.3 example. A purely structural rule with real cycle/path analysis is deferred (needs arbitrary-graph support).
- **Unit 7 — iteration counter = `count(tasks for to_node in run) − 1`**: the original pass is iteration 0; each loop-back adds one task for the looped-to node. Because the back edge's `to_node` (Coder) only gains tasks via the back edge, this counter is unaffected by the forward edge re-creating Reviewer tasks. `feedback_iteration_count` is also persisted on each loop-back task row for observability (the schema column exists for this).
- **Unit 7 — `AdvanceResult` with four explicit outcomes** (`next_task` | `completed` | `completed_forced` | `failed_no_match`) replaces Unit 6's `dict | None`: the worker maps each to a distinct run-state transition. Critically, `failed_no_match` and `completed_forced` are deliberate control-flow outcomes, NOT exceptions — only a genuinely missing next node raises and routes through `_record_run_failed_post_completion` (preserving the Unit 6 two-error-domain discipline).
- **Unit 7 — `completed_forced` overrides `no_matching_edge`**: per §9.3 a capped loop with nothing else matching completes with `forced_complete=true` (the sender's last output is accepted as final), even on a non-end node — it does NOT fail. `failed_no_match` only fires when a non-end node had edges, none matched, and no loop was capped.
- **Unit 7 — loop dispatch uses `msg_type="feedback"`**: a loop-back handoff is semantically feedback, not `task_output` (schema §11 allows both). Forward dispatches keep `task_output` (Unit 6 parity). `feedback_sent` is emitted on loop dispatch (atomic with the next task + message via `bus.persist_message`); `feedback_loop_capped` is emitted on cap (committed atomically with the forced-complete run update by the worker).
- **Unit 7 — true fan-out deferred (M1 from review)**: when >1 edge matches, only the first is dispatched (with a logged warning). `_get_edges_from` orders by `workflow_edges.id` so the choice is deterministic. Seed templates keep conditions mutually exclusive, so fan-out never fires; real simultaneous fan-out is deferred to a later unit.

#### TDD Evidence (Unit 7)
- **Failing tests written first:** `backend/tests/test_workflow_graph_semantics.py` (11 tests, `branch` 3-node fixture: Coder→Reviewer always; Reviewer→Coder REJECTED max_iter=2; Reviewer→Deployer APPROVED; a per-test closure-based `make_scripted_adapter`) authored before any Unit 7 implementation.
- **Failure observed (RED):** `pytest tests/test_workflow_graph_semantics.py -q` → **8 failed, 2 passed**. The 8 failures included the loop-cap tests hitting the bounded `_drain` guard (`AssertionError: drain exceeded 20 steps — likely an uncapped loop`) — proving Unit 6's traversal infinite-loops on REJECTED — and the no_matching_edge test asserting `failed` where Unit 6 wrongly returns `completed`. The 2 passing were the APPROVED-branch cases (Unit 6's single-match traversal already routes APPROVED→Deployer correctly); they served as regression guards through the rewrite.
- **Implementation done:** rewrote `app/services/workflow_graph.py` (`AdvanceResult`, loop-edge classification, `_resolve_cap`, `feedback_sent`/`feedback_loop_capped` emission, `no_matching_edge`/`completed_forced` outcomes); modified `workflow_worker.py` (outcome mapping in `process_dispatch_item`, `forced` param on `_record_run_completed`, new `_record_run_failed_no_match`).
- **Targeted test passed (GREEN):** `pytest tests/test_workflow_graph_semantics.py -q` → **11 passed** (10 initial + 1 added post-review for `feedback_iteration_count` persistence).
- **Full suite passed:** `pytest tests/ -q` → **82 passed, 1 skipped**.
- **S1 regression:** `pytest tests/test_agent_create.py tests/test_adapter.py -q` → **20 passed, 1 skipped**.
- **Unit 3/4/5/6 regression:** `pytest tests/test_workflow_api.py tests/test_message_bus.py tests/test_workflow_worker.py tests/test_workflow_graph_dispatch.py -q` → **51 passed**.

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
# Unit 7 RED:  pytest tests/test_workflow_graph_semantics.py -q -> 8 failed, 2 passed (uncapped-loop drain guard + no_matching_edge)
# Unit 7 GREEN: pytest tests/test_workflow_graph_semantics.py -q -> 11 passed (incl post-review feedback_iteration_count test)
# Unit 7 full suite: pytest tests/ -q -> 82 passed, 1 skipped
# Unit 7 S1 regression: pytest tests/test_agent_create.py tests/test_adapter.py -q -> 20 passed, 1 skipped
# Unit 7 Unit3+4+5+6 regression: pytest tests/test_workflow_api.py tests/test_message_bus.py tests/test_workflow_worker.py tests/test_workflow_graph_dispatch.py -q -> 51 passed
# Unit 7 gate: make ai-usage-check PHASE=S2_UNIT_7 -> PASS
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
- [x] Unit 7: confirmed `AcpGooseAdapter` and ACP lifecycle untouched — no adapter file changed, smoke gate not required
- [x] Unit 7: confirmed loop cap fires at exactly the §9.3 boundary (max_iter=2 → 2 loop-backs, 3rd capped); traced step-by-step and proven by `test_loop_cap_fires_at_boundary`
- [x] Unit 7: confirmed the forward "always" edge is never misclassified as a loop (forward flow not capped) — `condition != "always"` guard, proven by branch-selection + cap tests
- [x] Unit 7: confirmed `completed_forced`/`failed_no_match` are deliberate outcomes (not exceptions); the completed task is never rolled back (S5 asserts task stays completed on no_matching_edge)
- [x] Unit 7: confirmed two-error-domain discipline preserved — only a missing next node raises; Unit 6 graph-failure tests (`test_graph_failure_*`) still green
- [x] Unit 7: confirmed no SSE/approval/true-fan-out/retry/background-loop scope creep
- [x] Unit 7: confirmed Unit 3/4/5/6 + S1 behavior preserved (51 + 20 regression green)

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

**Unit 7 — TDD followed:** 11 tests authored and confirmed-failing (8 failed, 2 passed) before implementation. The RED signal was behavioral, not a collection error: the uncapped Unit 6 loop blew the bounded `_drain` step budget (`AssertionError: drain exceeded 20 steps`), and the no_matching_edge test asserted `failed` where Unit 6 returns `completed`. The 2 already-passing APPROVED-branch tests acted as regression guards through the rewrite. No spec deviations.

**Unit 7 — targeted review run (ce-correctness-reviewer):** **Verdict: Approve to commit.** No blocking or high findings. The reviewer traced the loop-cap boundary step-by-step (confirmed cap at exactly max_iterations with no off-by-one), verified the forward-edge-never-capped guard, and confirmed transaction atomicity on every outcome (completed_forced, failed_no_match, next_task early-return, exception path). Findings resolved/deferred:
- **M1 (medium, fan-out ordering) — partially resolved:** added deterministic `ORDER BY workflow_edges.id` to `_get_edges_from` so "take first eligible" is reproducible. True simultaneous fan-out (2+ matched non-loop edges) remains deferred (seed conditions are mutually exclusive, so it never fires).
- **M2 (medium, `max_iterations=0`) — deferred:** `0` currently means "loop never taken" (caps on first match). Spec §9.3 does not define `0`; rather than guess intent, deferred with a recorded note. Seed data uses ≥1 / null.
- **L1 (low, `iteration_count` semantics) — clarified in code:** added a comment documenting `iteration_count` = loop-backs already accepted (== cap at the boundary), not the skipped attempt. No behavior change; the value is asserted by `test_feedback_loop_capped_event_shape`.
- **L2 (low, docstring grammar) — fixed** in `_record_run_completed`.
- **Testing gap closed:** added `test_loop_task_records_feedback_iteration_count` asserting the `feedback_iteration_count` column is persisted (0,1,2) on loop-back task rows, not only in the event.

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

#### Review Tier Decision (Unit 7)
- **Classification: high-risk-unit-closeout.** Unit 7 modifies workflow orchestration, run state transitions (new `completed_forced` and `failed_no_match` outcomes), loop control, and event emission on the just-stabilized graph engine. Same tier as Units 5–6.
- **Minimum review: targeted correctness review required before commit.** Full `ce-adversarial-reviewer` not required — no ACP adapter, auth, external integration, or untrusted-input routing changed. No waiver.
- **Review run:** `ce-correctness-reviewer`, read-only, scoped to `workflow_graph.py` + `workflow_worker.py` + `test_workflow_graph_semantics.py`. **Verdict: Approve to commit.** Findings recorded and resolved/deferred above (M1 partially resolved, M2/fan-out deferred, L1/L2 fixed, one test gap closed). Re-validated after fixes: targeted 11 passed, full suite 82 passed/1 skipped.

#### `/ce-compound` Decision (Unit 7)
- **Defer to S2 phase closeout.** Unit 7 adds the fifth nugget: the loop-edge classification heuristic (`condition != "always"` AND target-already-executed) and the per-target-node iteration counter that together make a 2-cycle feedback cap land on the spec boundary without polluting the count. This is a reusable pattern for bounded feedback loops in graph execution. Capture with the Units 3–6 nuggets as one coherent `docs/solutions/workflow-issues/` entry at S2 closeout. No `docs/solutions/` file created this unit.

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
- **Unit 7 — loop cap, no_matching_edge, branch selection: DONE.** The two Unit 6 deferrals (loop cap, no_matching_edge failure) are resolved; conditional branch selection across all edges is correct. The seed templates (dev_pipeline, research_pipeline) now run safely without infinite loops.
- **Unit 7 — true fan-out (M1) deferred:** when ≥2 edges match, only the first (by `workflow_edges.id` order) is dispatched, with a logged warning. Simultaneous multi-edge fan-out / parallel branch execution is deferred; seed conditions are mutually exclusive so it never fires today.
- **Unit 7 — `max_iterations=0` semantics (M2) deferred:** `0` currently caps on the first match (loop never taken). §9.3 does not define `0`; intent confirmation + a boundary test deferred. Seed uses ≥1 / null.
- **Unit 7 — purely structural loop detection deferred:** the loop-edge heuristic relies on `condition != "always"`. A graph with an "always" back edge (an unconditional loop) is not handled; real cycle/path analysis for arbitrary graphs is deferred (out of two-day scope; seed loops are all conditional).
- **Unit 7 — stale dispatch / terminal-state guard still deferred:** unchanged from Unit 6.
- **Units 8+**: Approval gate (§13/§14: pre-dispatch pause, `approval_required`/`approval_resolved`, approve/reject endpoints, `awaiting_approval` state), SSE endpoint (`/events`), replay (`/runs/{id}/events`), S2 Run View UI (§17.2) — not started.

#### Architectural or Specification Amendments
- No amendments to BUILD_SPEC.md or SYSTEM_DESIGN.md required.
- Confirmed: `channel_connections.channel_id NOT NULL` with no server default makes pre-S3 persistence impossible without schema change. Architecture is correct as-is.
- Noted (no change required): BUILD_SPEC §9.1 ("creates row status=pending") vs §10 ("pending → running : start_workflow_run") is a minor internal tension; Unit 3 follows §9.1's explicit `pending` since the worker that performs the transition is out of scope.

---

### Story: S2-REM — Remittance Comparison workflow (Phase A: U1 fixtures + U2 types)
**Date:** 2026-06-14
**Status:** [x] In Progress  [ ] Complete  [ ] Blocked

> **Gate limitation (recorded per instruction):** `make ai-usage-check` only
> recognizes `S2` / `S2_UNIT_N` phase names tied to the original workflow-engine
> units. There is no phase for the remittance plan's U1/U2
> (`make ai-usage-check PHASE=S2_REMITTANCE_UNIT_1` → "Unrecognized PHASE").
> This entry is therefore maintained **manually**. Plan source:
> `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md`.

#### AI Tools and Models Used
- Claude Opus 4.8 (1M context) via Claude Code — planning (ce-plan), multi-persona
  doc review (ce-doc-review), and this Phase A implementation (ce-work).
- 7 reviewer subagents during the plan's doc-review pass (coherence, feasibility,
  product-lens, security-lens, scope-guardian, adversarial, design-lens).

#### Important Prompts
- `/ce-work` scoped to "Phase A only — U1 fixtures + U2 types"; explicit do-not-implement
  list (U3–U12, Telegram, graph/worker changes); do-not-commit; TDD where practical.
- Clarifying question raised before coding: the prompt asked for a third compliance
  route `COMPLIANCE=NEEDS_REVIEW` described as "in the plan", but the plan defines
  Compliance as binary. User chose to **add** NEEDS_REVIEW as a third route.

#### Decisions Made with AI Assistance
- **NEEDS_REVIEW added** as a third `ComplianceStatus` + sentinel + fixture case
  (user decision). Scope divergence from the plan — see Amendments.
- **Sentinel routing tokens** (`COMPLIANCE=<STATUS>`, `ANALYST=<STATUS>`) carried
  from plan KTD6 into the type constants — anchored `=` defeats the unanchored
  substring matcher's fail-open collision.
- **`cop_received` convention** fixed as `round((amount_usd - fee_usd) * rate_cop)`
  and documented in the fixture `_note` so U7 scoring aligns with the data.
- **Fail-closed `from_dict` validation** — status literals raise `ValueError` on
  unknown values (the plan's "status literals reject invalid values" verification;
  Python `Literal` is not enforced at runtime, so explicit checks were added).
- **`compliance_cases.json` fixture added** (beyond the plan's two fixtures) to hold
  example compliance outputs so the sentinel exactness + collision guard can be
  asserted at the data layer without implementing U4/U5.
- **`edge_matches` imported read-only** in the fixtures test (no change to
  `workflow_graph.py`) so the collision guard runs through the REAL matcher.

#### Validation Commands Run
```bash
# TDD red (before implementation)
python3 -m pytest tests/test_remittance_types.py tests/test_remittance_fixtures.py -q
#   → ModuleNotFoundError: No module named 'app.domain'   (expected red)

# TDD green (after implementation)
python3 -m pytest tests/test_remittance_types.py tests/test_remittance_fixtures.py -q
#   → 31 passed in 0.54s

# Full suite (regression)
python3 -m pytest tests/ -q
#   → 113 passed, 1 skipped in 8.53s

# AI_USAGE gate (unsupported phase — limitation recorded above)
make ai-usage-check PHASE=S2_REMITTANCE_UNIT_1
#   → Unrecognized PHASE 'S2_REMITTANCE_UNIT_1'.
```

#### Manual Review Performed
- [x] Reviewed diff for scope creep — Phase A only; no U3–U12, no Telegram, no
      graph/worker changes. The one addition beyond the plan's file list
      (`compliance_cases.json`) is justified above and serves the required tests.
- [x] Verified no secrets — fixtures are fabricated demo data, labeled `_note`;
      no tokens/keys/chat_ids.
- [x] Checked BUILD_SPEC/plan contracts — TransferBrief/ComplianceResult/AnalystResult
      field shapes match the plan's data contracts; sentinel convention matches KTD6.
- [x] Ran the required tests and confirmed green (31 Phase A + full suite).

#### Review Findings or Mistakes Caught
- Collision-guard test proves the prior fail-open bug is closed: a `COMPLIANCE=FLAGGED`
  output whose prose contains "cleared" returns `edge_matches("COMPLIANCE=CLEARED", out)
  == False` through the real matcher.
- Caught the plan-vs-prompt conflict (NEEDS_REVIEW) before writing code rather than
  silently picking one interpretation.

#### Deferred or Blocked Work
- U3 Research, U4 Compliance engine, U5 ComplianceAdapter, U6 worker selection,
  U7 scoring/analyst, U8 seed, U9 workflow tests, U10 docs, U11 canvas, U12 loop
  threading — all out of Phase A scope.
- **NEEDS_REVIEW semantics undefined:** what triggers it and where it routes is a
  U4 (engine) + U8 (seed graph) decision. Phase A only makes it a representable
  status/sentinel/fixture case.
- **Plan amendment owed:** KTD6, U4, U5, U8 must be updated to define NEEDS_REVIEW
  before those units are built (see Amendments).

#### Architectural or Specification Amendments
- **Scope divergence (NEEDS_REVIEW):** the committed plan defines Compliance as
  binary (CLEARED/FLAGGED). Per execution-time user decision, a third route
  NEEDS_REVIEW is now representable in types + fixtures. The plan body was NOT
  edited during this ce-work run (routing semantics are a genuine U4/U8 decision,
  not a guess). Before U4/U5/U8: update plan KTD6 (sentinel set), U4 (trigger rule),
  U5 (adapter output), U8 (seed edge + route target), and record in DECISION_LOG.md.

#### Final Completion Status
- [x] Phase A units U1 + U2 implemented test-first
- [x] Required tests green (31 Phase A; 113 passed / 1 skipped full suite)
- [ ] Commit made — **pending user approval** (do-not-commit per prompt)
- [x] AI_USAGE.md updated (this entry, manual)
- ce-compound decision: **defer** — accumulate with the broader S2/remittance
  closeout; no standalone learning warrants `docs/solutions/` yet.

---

### Story: S2-REM — Remittance Comparison workflow (Phase B: U3 Research helper)
**Date:** 2026-06-14
**Status:** [x] In Progress  [ ] Complete  [ ] Blocked

> Same gate limitation as Phase A: `make ai-usage-check` has no phase name for the
> remittance plan's units, so this entry is maintained manually. Plan source:
> `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U3).

#### AI Tools and Models Used
- Claude Sonnet 4.6 via Claude Code — read the U3 spec + existing contracts/fixtures,
  then TDD implementation (failing test → helper → green). (Commits carry the
  standard Claude co-author trailer.)

#### Important Prompts and Key Decisions
- Scoped to "U3 only — Research parsing / fixture-backed brief assembly"; explicit
  do-not list (no U4 compliance engine, no adapter, no worker/graph changes, no
  Telegram, no frontend); do-not-commit; test-first.
- Decisions:
  - `assemble_brief(text, *, memory_defaults, fixture_path, live_lookup=None)` —
    pure, dependency-injected. `live_lookup=None` makes the fixture fallback the
    default path so live rates are never fabricated (R3).
  - Missing provider rate fields are returned as `missing_fields` gap labels
    (e.g. `"western_union.rate_cop"`) via a `(quote, gaps)` builder — NOT raised.
    This deliberately bypasses `ProviderQuote.from_dict`, which would `KeyError`
    on the very field U3 must report (R4).
  - Modality detection: digital keywords (bank/account/wise/digital) → `digital_send`;
    otherwise `cash_send`. Cash quotes WU+MG; digital adds Wise (R2).
  - Source split (KTD3): provider quotes + `sender_profile` from the fixture;
    locality/currency from injected `memory_defaults`; amount + modality from text.

#### TDD Evidence (U3)
- RED:   `pytest tests/test_remittance_research.py -q` → `ModuleNotFoundError:
         No module named 'app.domain.remittance.research'` (expected red).
- GREEN: `pytest tests/test_remittance_research.py -q` → 6 passed.
- 6 scenarios: cash parse (type/amount/WU+MG, no Wise), digital parse (Wise present),
  fixture-fallback default, missing-field labeling, memory-default locality fill,
  amount-without-`$` parse.
- **Pre-commit cleanup pass** (see Review Findings): 3 additional tests added → 9 total.
  New: `test_location_containing_bank_does_not_force_digital` (word-boundary regression),
  `test_digital_includes_western_union_and_moneygram` (R2 provider completeness),
  `test_missing_field_yields_none_quote_not_partial` (gap-is-None contract).

#### Validation Commands Run
```bash
# Initial TDD green (6 tests)
python3 -m pytest tests/test_remittance_research.py -q   # → 6 passed
python3 -m pytest tests/test_remittance_*.py -q          # → 37 passed
python3 -m pytest tests/ -q                              # → 119 passed, 1 skipped

# After pre-commit cleanup pass (9 tests — word-boundary fix + 3 new coverage tests)
python3 -m pytest tests/test_remittance_research.py -q   # → 9 passed
python3 -m pytest tests/test_remittance_*.py -q          # → 40 passed
python3 -m pytest tests/ -q                              # → 122 passed, 1 skipped
```

#### Manual Review Performed
- [x] Fixture-first: `live_lookup` defaults to `None` → `data_source="fixture"`; no live invention.
- [x] Missing fields returned as recoverable gaps, not exceptions.
- [x] Deterministic: inputs are text + injected fixture + memory dict; no clock/random/network/DB.
- [x] No Goose, no DB import; no worker/graph/runtime behavior changed.
- [x] No secrets (fixtures are labeled demo data).
- [x] No frontend files touched; scope is `research.py` + its test only.

#### Review Findings or Mistakes Caught
- TDD surfaced the `from_dict` KeyError trap before it was written: the missing-field
  test forced the `(quote, gaps)` return shape instead of a crashing constructor.
- **Keyword matching false-positive — FIXED in pre-commit cleanup pass:** `"bank" in text`
  matched "Burbank", misclassifying `"send $500 cash to Burbank"` as `digital_send`.
  Fixed by replacing the `_DIGITAL_KEYWORDS` tuple + `any(keyword in low ...)` loop with
  `_DIGITAL_RE = re.compile(r"\b(?:digital|bank|wise|account)\b", re.IGNORECASE)` and
  `_DIGITAL_RE.search(text)`. Regression test added:
  `test_location_containing_bank_does_not_force_digital`.
- **R2 provider coverage gap — FIXED in pre-commit cleanup pass:** the `test_digital_parse_includes_wise`
  test only asserted `wise is not None`; a regression dropping WU+MG from `digital_send`
  would have passed. Added `test_digital_includes_western_union_and_moneygram` asserting
  all three providers are non-None on a digital request.
- **Gap-is-None not pinned — FIXED in pre-commit cleanup pass:** the missing-field test
  asserted the gap label was recorded but not that `brief.western_union is None`. A bug
  constructing a partial quote while also recording the gap would have slipped through.
  Added `test_missing_field_yields_none_quote_not_partial` asserting the gapped provider
  is `None` in the output brief.

#### Deferred or Blocked Work
- **Amount parser takes first number in string** — `"2 payments of $500"` → `2.0`. The
  demo corridor's inputs are single-number requests, so this does not affect correctness
  today. A `$`-anchored heuristic or structured extractor is the right fix at 10x scale.
- **Natural-language number parsing** — `"send five hundred dollars"` → `amount_usd=0.0`
  (fixture fallback). Out of scope for the deterministic demo helper; LLM extractor at 10x.
- **Whole-provider-block-absent branch test** — when an entire provider block (e.g. the
  entire `"western_union"` key) is absent from the fixture, `_build_quote` returns
  `(None, [name])` (a provider-level gap label). The fixture always supplies all three
  providers, so this path is unreachable in current tests. Deferred — low risk for demo.
- **`live_lookup` hook coverage** — the hook's path (`data_source="live"`, returned data
  consumed) is untested. The hook is DI and currently unused by default; deferred.
- **Structured extractor at 10x scale** — the deterministic keyword/regex parser is
  the demo-tier implementation. A structured/LLM extractor with output normalization is
  the production path; deferred beyond S3.
- U4 Compliance engine: implemented (see entry below).
- U5 ComplianceAdapter and onward — not started.

#### Review Tier Decision (U3)
- Light self-review only. Rationale: small (~114 LOC), pure function, fully covered by
  9 deterministic tests (post-cleanup), no runtime/security surface. No multi-persona
  review warranted.

#### `/ce-compound` Decision (U3)
- Defer — accumulate with the broader remittance closeout; no standalone learning
  warrants `docs/solutions/` yet.

---

### Story: S2-REM — Remittance Comparison workflow (Phase B: U4 Compliance rules engine)
**Date:** 2026-06-14
**Status:** [x] In Progress  [ ] Complete  [ ] Blocked

> Same gate limitation as Phase A/B: `make ai-usage-check` has no phase name for the
> remittance plan's units, so this entry is maintained manually. Plan source:
> `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U4).

#### AI Tools and Models Used
- Claude Sonnet 4.6 via Claude Code — read U4 spec + existing contracts/fixtures +
  compliance_rules.json + compliance_cases.json, then TDD (failing test → engine → green).

#### Important Prompts and Key Decisions
- Scoped to "U4 only — compliance rules engine"; explicit do-not list (no U5 adapter,
  no worker, no graph changes, no Telegram, no frontend); do-not-commit; test-first.
- Decisions:
  - `screen(brief, *, rules_path)` — pure function. Five rules evaluated in priority order;
    first failure short-circuits with FLAGGED. Rules load from `rules_path`, never hardcoded.
  - `screen_from_dict(raw_dict, *, rules_path)` — input-validation seam. The typed
    `SenderProfile` cannot represent a missing `previously_flagged` field, but the raw
    adapter payload can omit it. A missing flag is FLAGGED (fail-closed, KTD3). This seam
    catches the gap before `TransferBrief.from_dict()` would silently KeyError or default.
  - `format_output(result)` — adapter-ready text helper with sentinel on line 1 (KTD6).
    Kept in `compliance.py` (not the adapter) so tests can verify sentinel and
    collision-guard properties without importing U5, and U5 can import rather than re-implement.
  - NEEDS_REVIEW not emitted: all five configured rules resolve to CLEARED or FLAGGED.
    NEEDS_REVIEW is a representable status (types.py) whose trigger conditions are deferred
    to U8 (seed graph). Documented in the module docstring.
  - Corridor check: simple send/receive pair lookup. Fail-closed when the pair is absent
    (FLAGGED), including when `supported_corridors` is empty. The providers list inside
    each corridor entry is informational; the check does not restrict routing by provider.
  - AML rule: cash send strictly GREATER THAN threshold → FLAGGED. At-the-threshold ($3000)
    → CLEARED. **Threshold semantics: EXCLUSIVE (`>`)**, matching the plan's explicit
    `amount_usd > aml_reporting_threshold_usd` operator. The `/ce:work` prompt phrased
    this as "at or above" (`>=`), which conflicts with the plan. The plan's Approach
    section is authoritative — it writes the actual Python operator. Real-world FinCEN CTR
    uses at-or-above for $10,000; this demo engine intentionally uses the plan's exclusive
    definition. Decision recorded after pre-commit threshold review (Option B chosen).
  - ID rule: cash send GREATER THAN OR EQUAL TO threshold → note (never FLAGGED). Rule is
    cash-only; digital sends do not trigger it.

#### TDD Evidence (U4)
- RED:   `pytest tests/test_remittance_compliance.py -q` → `ModuleNotFoundError:
         No module named 'app.domain.remittance.compliance'` (expected red).
- GREEN: `pytest tests/test_remittance_compliance.py -q` → 25 passed.
- **Pre-commit threshold/sentinel cleanup pass** → 1 test comment strengthened + 1 new
  test added (sentinel-contamination guardrail) → 26 tests total.
- **Final targeted review cleanup pass** → 1 bug fix (sender_profile: null fail-closed
  gap — see Review Findings), 1 AML-cash-only docstring clarified, 1 new test
  (`test_null_sender_profile_fails_closed`) → 27 tests total.
- 27 scenarios covering: standard CLEARED ($500), ID note present/absent, AML threshold
  boundary (exclusive: $3000 → CLEARED, $3001 → FLAGGED), AML cash-only, restricted
  country (sender + recipient), unsupported corridor, empty corridors (fail-closed),
  previously-flagged sender, missing previously_flagged (fail-closed via screen_from_dict),
  null sender_profile (fail-closed — fixed in final review), screen_from_dict passthrough
  for valid input, sentinel line-1 (CLEARED and FLAGGED), collision-guard prose ("cleared"
  lowercase), sentinel-contamination guard (exact "COMPLIANCE=CLEARED" token in FLAGGED
  output, all 5 FLAGGED paths enumerated), collision guard via fixture case,
  ComplianceResult round-trip, natural-language-status rejection, and unknown-status
  rejection.

#### Validation Commands Run
```bash
# TDD red (before implementation)
python3 -m pytest tests/test_remittance_compliance.py -q
#   → ModuleNotFoundError: No module named 'app.domain.remittance.compliance'

# TDD green (after implementation)
python3 -m pytest tests/test_remittance_compliance.py -q
#   → 25 passed in 0.61s

# Remittance-suite regression (initial)
python3 -m pytest tests/test_remittance_*.py -q
#   → 65 passed in 0.51s

# Full suite regression (initial)
python3 -m pytest tests/ -q
#   → 147 passed, 1 skipped in 7.61s

# After pre-commit threshold/sentinel cleanup (1 test comment + 1 new guardrail test)
python3 -m pytest tests/test_remittance_compliance.py -q
#   → 26 passed in 0.47s
python3 -m pytest tests/test_remittance_*.py -q
#   → 66 passed in 0.52s
python3 -m pytest tests/ -q
#   → 148 passed, 1 skipped in 7.70s

# After final targeted review cleanup (null-profile fix + 1 new test + comment clarity)
python3 -m pytest tests/test_remittance_compliance.py -q
#   → 27 passed in 0.61s
python3 -m pytest tests/test_remittance_*.py -q
#   → 67 passed in 0.61s
python3 -m pytest tests/ -q
#   → 149 passed, 1 skipped in 8.65s
```

#### Manual Review Performed
- [x] Confirmed no Goose, no DB, no network imports in compliance.py.
- [x] Confirmed format_output always produces a KTD6 sentinel on line 1.
- [x] Confirmed FLAGGED output can never contain "COMPLIANCE=CLEARED" (format_output
      only emits the result's own sentinel, not a cross-sentinel string).
- [x] Confirmed screen_from_dict fails closed for missing previously_flagged without
      defaulting to False or raising.
- [x] Confirmed AML rule is cash-only (digital $5000 → CLEARED in tests).
- [x] Confirmed corridor check fails closed for empty supported_corridors list.
- [x] No secrets in fixture files (demo data labeled _note).
- [x] No frontend, worker, graph, adapter, or seed files touched.

#### Review Findings or Mistakes Caught
- None during TDD authoring — all 25 tests passed on the first implementation run.
  The input-validation seam (screen_from_dict) was designed before writing to avoid the
  subtle trap: calling TransferBrief.from_dict() on a dict with a missing previously_flagged
  would raise a KeyError in SenderProfile.from_dict(), not return a ComplianceResult.
  The seam intercepts this before construction.
- **NB1 — `sender_profile: null` raised TypeError instead of failing closed — FIXED in
  final targeted review:** `brief_dict.get("sender_profile", {})` returns the explicit
  `None` value (not the `{}` default) when the key is present with a null value. Then
  `"previously_flagged" not in None` raises `TypeError`. Fixed by changing the call to
  `brief_dict.get("sender_profile") or {}`, which collapses both absent-key and null-value
  into an empty dict. The empty dict lacks `previously_flagged`, so the seam returns
  FLAGGED (fail-closed, KTD3). New test: `test_null_sender_profile_fails_closed`, which
  also verifies the FLAGGED sentinel appears on line 1 of the formatted output.
- **NB2 — AML cash-only test comment was misleading — FIXED:** the comment said "may or
  may not clear depending on corridor/sender" while unconditionally asserting CLEARED.
  Replaced with a precise docstring stating exactly what is proved: for the default brief
  (USD→COP, non-flagged sender, no restricted countries), a digital $5000 is CLEARED
  because the AML rule is cash-only and no other rule triggers on the default parameters.
- **NB3 — `format_output` NEEDS_REVIEW body uses notes path (not issue) — DEFERRED:**
  if NEEDS_REVIEW were ever emitted, its body would be `" ".join(result.notes)`, not
  `result.issue`. This is not a current bug (NEEDS_REVIEW is never emitted by this
  engine — documented in the module docstring). U5 should not assume format_output handles
  NEEDS_REVIEW via issue. Deferred to U8 when NEEDS_REVIEW semantics are defined.

#### Deferred or Blocked Work
- **NEEDS_REVIEW trigger semantics** — representable in types.py but no rule in
  compliance_rules.json triggers it. Deferred to U8 (seed graph definition).
- **Corridor provider-level validation** — the current check finds the send/receive pair
  but does not verify the specific providers in `corridor["providers"]` are the ones
  actually quoted in the brief. This is fine for the demo (both WU and MG are always
  present in the fixture); a stricter check would cross into Analyst territory. Deferred.
- **Sender KYC and account_tier rules** — `kyc_verified` and `account_tier` are present
  in SenderProfile but no rule currently uses them. The NEEDS_REVIEW fixture case references
  "account tier and corridor combination" — this logic belongs with NEEDS_REVIEW semantics
  and is deferred to U8.
- **U5 ComplianceAdapter** — implemented; see entry below.
- **U6 worker adapter selection** — implemented; see U6 entry below.

#### Review Tier Decision (U4)
- **Classification: high-risk-lite.** U4 controls routing and fail-closed behavior for
  a compliance gate. Mistakes here mean a FLAGGED transfer reaching the Analyst (fail-open).
  The sentinel test and collision-guard test directly guard against the KTD6 substring
  collision. No adapter, no runtime, no DB — but the correctness stakes are high.
- **Minimum review: targeted correctness review.** Run before proposing commit.
  Full ce-adversarial-reviewer not required (pure function, no external integrations).
  Review scope: `compliance.py` + `test_remittance_compliance.py`.

#### `/ce-compound` Decision (U4)
- Defer — accumulate with the broader remittance closeout. The fail-closed seam
  (screen_from_dict) and format_output as a shared sentinel helper are reusable patterns,
  but capturing them now would be premature. Document at S2-REM phase closeout.

---

### Story: S2-REM — Remittance Comparison workflow (Phase B: U5 ComplianceAdapter)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Same gate limitation as Phase A/B: `make ai-usage-check` has no phase name for the
> remittance plan's units, so this entry is maintained manually. Plan source:
> `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U5).

#### AI Tools and Models Used
- Claude Sonnet 4.6 via Claude Code — read U5 spec + adapter interface + types + compliance
  engine, then TDD (failing test → adapter → green).
- ce-correctness-reviewer (compound-engineering) — targeted review post-initial-green;
  found one P1 blocking issue (F1) fixed before reporting.

#### Important Prompts and Key Decisions
- Scoped to "U5 only — ComplianceAdapter"; explicit do-not list (no worker/graph changes,
  no seed, no Telegram, no frontend, no Analyst/Research logic); do-not-commit; test-first.
- Decisions:
  - `ComplianceAdapter(host=..., port=..., *, rules_path=None)` — `host`/`port` accepted
    and ignored for swap-compatibility with `AcpGooseAdapter` constructor signature.
    `rules_path` is keyword-only for testability; defaults to `_DEFAULT_RULES_PATH`
    (the committed `backend/fixtures/compliance_rules.json`).
  - **Fail-closed on JSON parse AND on `TransferBrief.from_dict` failure (F1 fix):**
    the try/except wraps BOTH `json.loads` AND `screen_from_dict`. Before the review,
    only `json.loads` was wrapped; `from_dict` could raise `KeyError` (missing required
    field), `ValueError` (invalid enum), or `AttributeError` (non-dict JSON value like
    a list) after the except block, routing through the worker's `task_failed`/
    `workflow_failed` path with the issue suppressed. The fix catches all five exception
    types: `(json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError)`.
  - **Return FLAGGED, do not raise:** a raised exception routes through the worker's
    exception handler → `task_failed`/`workflow_failed`, leaving the run `failed` with
    the issue suppressed. The graph needs a visible FLAGGED terminal output (R10, plan
    KTD6). The adapter therefore returns `TaskResult(output=format_output(FLAGGED))` on
    every bad-input path.
  - **`on_event` never called:** a deterministic scripted adapter has no Goose stream to
    forward. The test passes a `_no_event` spy that raises on any call.
  - **`tokens_total=0`, `estimated_cost=0.0`:** `TaskResult` defaults; no explicit
    assignment needed. The adapter always returns `TaskResult(output=...)` and the
    dataclass defaults handle the rest.
  - **`_DEFAULT_RULES_PATH`:** `Path(__file__).resolve().parent.parent.parent / "fixtures"
    / "compliance_rules.json"` resolves from `backend/app/adapters/compliance_adapter.py`
    to `backend/fixtures/compliance_rules.json`. Verified against the committed layout.

#### TDD Evidence (U5)
- RED:   `pytest tests/test_compliance_adapter.py -q` → `ModuleNotFoundError:
         No module named 'app.adapters.compliance_adapter'` (expected red).
- GREEN: `pytest tests/test_compliance_adapter.py -q` → 14 passed.
- **Post-review fix (P1 F1) + 2 new tests** → 16 tests total.
- 16 scenarios covering: ABC conformance, swap-compatible constructor (host/port ignored),
  $500 CLEARED sentinel on line 1, tokens_total=0/estimated_cost=0.0, previously-flagged
  sender FLAGGED, missing previously_flagged fail-closed, null sender_profile fail-closed,
  malformed payload (non-JSON) fail-closed, empty payload fail-closed, incomplete JSON
  payload fail-closed (KeyError path — added post-review), non-dict JSON fail-closed
  (AttributeError path — added post-review), output matches format_output for CLEARED,
  output matches format_output for FLAGGED (AML threshold), FLAGGED output never contains
  COMPLIANCE=CLEARED across all 5 FLAGGED paths + edge_matches guard, on_event never
  called, health_check returns True without a server.

#### Validation Commands Run
```bash
# TDD red (before implementation)
python3 -m pytest tests/test_compliance_adapter.py -q
#   → ModuleNotFoundError: No module named 'app.adapters.compliance_adapter'

# TDD green (initial — 14 tests)
python3 -m pytest tests/test_compliance_adapter.py -q
#   → 14 passed in 0.43s

# After P1 fix + 2 new tests (16 tests)
python3 -m pytest tests/test_compliance_adapter.py -q
#   → 16 passed in 0.45s
python3 -m pytest tests/test_remittance_compliance.py -q
#   → 27 passed in 0.55s
python3 -m pytest tests/test_remittance_*.py -q
#   → 67 passed in 0.53s
python3 -m pytest tests/ -q
#   → 165 passed, 1 skipped in 7.94s
```

#### Manual Review Performed
- [x] Confirmed no Goose, DB, network, or worker imports in compliance_adapter.py.
- [x] Confirmed `on_event` is never called (test spy raises on any call; all 16 pass).
- [x] Confirmed fail-closed on every bad-input path (5 paths, all tested).
- [x] Confirmed KTD6 sentinel on line 1 for both CLEARED and FLAGGED outputs.
- [x] Confirmed FLAGGED output never contains COMPLIANCE=CLEARED (5-path enumeration +
      edge_matches guard through the real graph matcher).
- [x] Confirmed `tokens_total=0`, `estimated_cost=0.0` (TaskResult defaults; no LLM).
- [x] Confirmed `health_check()` returns True without a running Goose server.
- [x] No secrets in new files (fixture path and class definition only).
- [x] No worker, graph, seed, frontend, Telegram, or planning doc files touched.

#### Review Findings or Mistakes Caught
- **F1 (P1) — fail-closed try/except too narrow — FIXED before commit:** the initial
  implementation wrapped only `json.loads` in the try/except. A structurally valid JSON
  payload missing required `TransferBrief` fields (e.g., `{"amount_usd": 500}` with no
  `transfer_type`) caused `from_dict` to raise `KeyError` after the except block, routing
  through the worker's `task_failed` path rather than returning `COMPLIANCE=FLAGGED`.
  A non-dict JSON value (list, string) similarly raised `AttributeError` in
  `brief_dict.get("sender_profile")`. Fixed by widening the except to wrap both
  `json.loads` and `screen_from_dict`, catching five exception types:
  `(json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError)`.
  Two new tests added: `test_invoke_incomplete_json_payload_fails_closed` and
  `test_invoke_non_dict_json_fails_closed`.
- **F2 (P2, non-blocking) — test_output_matches_format_output is mildly tautological:**
  both sides call `format_output` on the same result, so a bug in `format_output` itself
  would be invisible. The real routing correctness signal comes from the sentinel-line-1
  tests. Noted; not changed — the tautology is acceptable for contract documentation.

#### Deferred or Blocked Work
- **NEEDS_REVIEW sentinel path not tested:** the compliance engine never emits
  NEEDS_REVIEW (deferred to U8). When U8 activates that route, a test for
  `COMPLIANCE=NEEDS_REVIEW` on line 1 must be added.
- **`FileNotFoundError` if rules_path missing:** `_load_rules` (in compliance.py) would
  raise `FileNotFoundError` if the rules file is absent; this is not in the except clause
  and would escape to the worker. For the demo the file is committed; deferred to production
  hardening.

#### Review Tier Decision (U5)
- **Classification: high-risk-lite.** U5 is the adapter seam that the worker will call
  for the Compliance node. Fail-open bugs here mean a FLAGGED transfer reaches the Analyst.
  The correctness reviewer found one P1 blocking issue (F1) and it was fixed.
- **Review run:** targeted correctness review (ce-correctness-reviewer), read-only,
  scoped to `compliance_adapter.py` + `test_compliance_adapter.py`.
  **Verdict: Hold for fixes → fixed before commit.** All P1 issues resolved.
  P2 findings noted and addressed or documented.

#### `/ce-compound` Decision (U5)
- Defer to S2-REM phase closeout. U5 adds the fail-closed adapter pattern (one except
  wrapping the full parse+screen chain rather than splitting JSON parse from domain
  validation) as a reusable design decision for scripted adapters. Capture with U3–U4
  learnings at phase closeout.

---

### Story: S2-REM — Remittance Comparison workflow (Phase B: U6 worker adapter selection)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U6).

#### AI Tools and Models Used
- Claude via Cursor — read worker + compliance adapter, TDD W14 test, `_pick_adapter` + `SCRIPTED_AGENTS`.

#### Important Prompts and Key Decisions
- Scoped to U6 only: worker adapter selection; no graph/seed/analyst changes.
- `SCRIPTED_AGENTS = {"Compliance": ComplianceAdapter}` on `WorkflowWorker`.
- `_pick_adapter(agent)` returns scripted class for registry hits; otherwise `adapter_cls`.
- W14 proves `FakeAdapter.invoke_count == 0` for Compliance agent; output starts with `COMPLIANCE=CLEARED`.

#### TDD Evidence (U6)
- Added `test_compliance_agent_uses_scripted_adapter` (W14) with `compliance_seed` fixture.
- Full suite: `pytest tests/ -q` → 173 passed, 1 skipped.

#### Manual Review Performed
- [x] No graph, seed, frontend, or analyst files touched.
- [x] Non-scripted agents still use injected `adapter_cls` (W8 regression intact).

---

### Story: S2-REM — Remittance Comparison workflow (Phase B: U7 Analyst scoring + report)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U7).

#### AI Tools and Models Used
- Claude via Cursor — test-first analyst/scoring per KTD5 (50/30/20 weights, digital location equalization).

#### Important Prompts and Key Decisions
- `scoring.py` — pure min-max normalization; `score_breakdown` exposed for digital equalization tests.
- `analyst.py` — `analyze(brief, *, reports_dir, compliance_notes=None)`; NEEDS_MORE_DATA when gaps exist;
  writes `transfer_comparison.md`; `format_output` for KTD6 sentinel + Telegram body.
- Tie-break on equal weighted scores → higher `cop_received`.
- Default fixture cash brief: MoneyGram wins on cop_received tie-break.

#### TDD Evidence (U7)
- 8 tests in `test_remittance_analyst.py`: WU winner scenario, digital equalization, tie-break,
  NEEDS_MORE_DATA, report write, telegram shape.
- Full suite: `pytest tests/ -q` → 173 passed, 1 skipped.

#### Manual Review Performed
- [x] No worker, graph, seed, adapter, or frontend files touched.
- [x] Scoring split from I/O per plan.

---

### Story: S2-REM — Remittance Comparison workflow (Phase D: U8 seed replacement)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U8).

#### AI Tools and Models Used
- Claude via Cursor — ce-work execution; test-first `test_seed_remittance.py`, then `populate_seed` refactor.

#### Important Prompts and Key Decisions
- Replaced Research Pipeline with Remittance Comparison; removed Publisher; Researcher → Research.
- Added Compliance agent; KTD6 edge conditions from `types.py` sentinels.
- Channel connection on Research → `trigger_workflow_id` = remittance workflow.
- Extracted `populate_seed(conn)` for testability; `seed()` wraps init_db + engine.begin.
- Dev Pipeline untouched; guardrails seeded from existing columns (max_cost_per_run deferred).

#### TDD Evidence (U8)
- 7 tests in `test_seed_remittance.py`.
- Full suite: `pytest tests/ -q` → 181 passed, 1 skipped.

---

### Story: S2-REM — Remittance Comparison workflow (Phase D: U9 workflow integration tests)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U9).

#### AI Tools and Models Used
- Claude via Cursor — ce-work execution; integration tests exposed graph handoff gaps fixed in f2ef1ef.

#### Important Prompts and Key Decisions
- Programmable fake for Research/Analyst; Compliance always real.
- Engine fixes (U9 blockers): forward ``task_output`` handoff; back-edge loop detection via ``position_x``.
- Six scenarios including real ``analyst.analyze`` terminal routing (F3 anti-laundering guard).

#### TDD Evidence (U9)
- 6 tests in `test_remittance_workflow.py`.
- Full suite: 187 passed, 1 skipped.

---

### Story: S2-REM — Remittance Comparison workflow (Phase C: U12 loop-back input threading)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U12).

#### AI Tools and Models Used
- Claude via Cursor — test-first change to `_dispatch_next` `is_loop` branch only.

#### Important Prompts and Key Decisions
- `compose_loop_back_input(task_prompt, task_output)` appends delimited feedback block.
- Forward (`always`) dispatch unchanged; same string on `agent_tasks.input` and enqueue item.
- S10 test: loop-back Coder task contains prompt + REJECTED sender output.

#### TDD Evidence (U12)
- `test_loop_back_input_contains_prompt_and_sender_output` (S10).
- Graph suites: 32 passed; full suite 174 passed, 1 skipped.

---

### Story: S2-REM — Remittance Comparison workflow (Phase E: U10 README + BUILD_SPEC)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U10).

#### AI Tools and Models Used
- Claude via Cursor — ce-work; BUILD_SPEC first, README second; examples cross-checked against `analyst.analyze` + `compliance.screen_from_dict`.

#### Important Prompts and Key Decisions
- Demo beats 5–6 realigned to Remittance Comparison; primary path pinned to single-pass CLEARED → RECOMMENDATION.
- §15 outbound send point fixed (terminal node, not Publisher); trigger prefix `run remittance:`.
- README Remittance section with bold compliance disclaimer; implemented vs deferred table (S3 Telegram).

#### Verification (U10 checklist)
- [x] README Remittance subsection with disclaimer, architecture, scoring, examples, limitations
- [x] Examples match actual U7/U4 output shapes (MoneyGram recommendation; $3500 FLAGGED)
- [x] BUILD_SPEC beats 5–6 reference remittance; research_pipeline marked superseded
- [x] No secrets in examples

---

### Story: S2-REM — Remittance Comparison workflow (Phase E: U11 frontend canvas mock sync)
**Date:** 2026-06-14
**Status:** [ ] In Progress  [x] Complete  [ ] Blocked

> Plan source: `docs/plans/2026-06-14-001-feat-remittance-comparison-workflow-plan.md` (U11).

#### AI Tools and Models Used
- Claude via Cursor — ce-work; ported Canvas/screens from `feat/frontend-design-foundation` via path checkout (no merge); aligned `mockData.ts` winner/telegram with U7 (MoneyGram).

#### Important Prompts and Key Decisions
- Remittance template is default tab: Research → Compliance → Analyst (no Publisher).
- FLAGGED exit rendered as dashed red stub (no false solid edge — KTD2 end-node fallthrough).
- Analyst→END shown as dashed `RECOMMENDATION ⤳ done` fallthrough, not a seeded ALWAYS edge.
- RunView cleared scenario banner/events derive winner from `REMITTANCE_CLEARED.winner`.

#### Verification (U11 checklist)
- [x] `npx tsc --noEmit` clean in `frontend/`
- [x] Both templates (remittance + dev) in Canvas tabs
- [x] FLAGGED path represented without false edge
- [x] Mock payoff matches U7 ($500 cash → MoneyGram recommendation)

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
