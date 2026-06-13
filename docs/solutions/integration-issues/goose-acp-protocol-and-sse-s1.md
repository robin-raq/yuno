---
title: Goose ACP protocol drift and SSE lifecycle (S1)
date: 2026-06-13
category: integration-issues
module: runtime-adapter
problem_type: integration_issue
component: service_object
symptoms:
  - "make smoke-goose fails with RuntimeError: Goose did not return acp-connection-id header"
  - "Unit tests pass but live ACP session fails or captures zero tool_call events"
  - "JSON-RPC responses matched incorrectly when multiple in-flight requests share one SSE stream"
root_cause: wrong_api
resolution_type: code_fix
severity: high
tags:
  - goose
  - acp
  - sse
  - json-rpc
  - smoke-gate
  - s1
related_components:
  - task_service
  - smoke_gate
---

# Goose ACP protocol drift and SSE lifecycle (S1)

## Problem

S1 implemented `AcpGooseAdapter` against the June spike's ACP assumptions. Unit tests with mocks passed, but the live smoke gate failed until the adapter was rewritten for Goose 1.37.0's current protocol. Several adversarial-review fixes (JSON-RPC id correlation, session cleanup, isolated DB sessions) remain load-bearing.

## Symptoms

- `GET /acp` without headers returns HTTP 400: `Bad Request: Acp-Connection-Id header required`
- Opening SSE first to obtain `acp-connection-id` fails on current Goose — connection id comes from synchronous `initialize` POST response header
- `session/prompt` rejects `{messages: [...]}` — requires `{sessionId, prompt: [{type: "text", text: "..."}]}`
- Event payloads use `params.update.sessionUpdate` as a string discriminator, not `params.sessionUpdate.type`
- Smoke gate passes only after port 3284 is free (leftover `goose serve` causes immediate exit)

## What Didn't Work

- **Single outer SSE for full lifecycle** (June spike / adversarial fix narrative): Opening one connection-level SSE before `initialize` and keeping it open for `session/new` + `session/prompt`. Superseded — Goose now issues conn id on sync `initialize` POST; session phases use scoped SSE streams.
- **Shape-based JSON-RPC matching**: Breaking on the first SSE message containing `"result"`. Fixed by correlating on `data.get("id") == rpc_id`.
- **Competing SSE connections** on the same conn id: Caused routing corruption. Fixed by eliminating duplicate streams and using a separate httpx client for session-scoped prompt SSE.
- **Shared AsyncSession for event persistence**: Intermediate commits corrupted the outer task transaction. Fixed with fresh `AsyncSessionLocal()` per event.
- **Relying on unit tests alone**: Mocks validated assumed protocol; only `make smoke-goose` exposed drift.

## Solution

### Current Goose 1.37.0 lifecycle (verified 2026-06-13)

1. `POST /acp` `initialize` (no conn header) → read `acp-connection-id` from **response header**; validate sync JSON body for errors
2. Open connection-level SSE with `Acp-Connection-Id` + `Accept: text/event-stream`
3. `POST session/new` → read `sessionId` from SSE correlated by request id
4. Close connection SSE; open **separate** session-scoped SSE (separate httpx client) with both `Acp-Connection-Id` and `Acp-Session-Id`
5. Open session SSE **before** `POST session/prompt`; correlate final result by prompt request id
6. `try/finally` → `session/close` on all exit paths

Reference: `backend/app/adapters/acp_goose.py`

### JSON-RPC correlation (Blocking finding)

Always match responses by request id:

```python
if data.get("id") == session_rpc_id and "result" in data:
    session_id = data["result"]["sessionId"]
    break
```

Never break on shape alone (`"result" in data` without id check).

### Task failure safety

On adapter failure, record failure in a **fresh** DB session so the task row is not left in `running`:

```python
async with AsyncSessionLocal() as fail_db:
    await fail_db.execute(update(agent_tasks).where(...).values(status="failed", ...))
```

Reference: `backend/app/services/task_service.py`

### Preamble injection (partial)

Sanitize user-controlled memory and skill values before composing preamble (`_sanitize_user_content`). **Follow-up:** sanitize `system_prompt` too.

### Smoke gate requirement

Run `make smoke-goose` before declaring ACP integration complete. Gate must:

- Start real `goose serve` with native provider
- Capture ≥1 real `tool_call` event
- Verify on-disk artifact
- Save frames to `data/smoke/frames.json` (local; gitignored)

Unit tests alone are insufficient for protocol integration.

## Why This Works

Goose's ACP surface changed after the spike doc was written. The adapter must follow live header/param/event shapes, not documented assumptions. Id-correlated JSON-RPC prevents cross-talk on shared SSE streams. Isolated DB sessions prevent transaction corruption during long-running adapter calls. Live smoke validates the same code path production uses.

## Prevention

- Run **`make smoke-goose`** on every adapter change; treat port conflicts as environment failures, not code failures
- Add **frame replay test** parsing saved `frames.json` through `_parse_session_update` (BUILD_SPEC intent; deferred to pre-S6)
- Wire **`TaskInput.extensions` → `mcpServers`** when per-agent tools matter (deferred S2+)
- Map **`tool_call` tool names** from new event fields (live frames currently show `tool: unknown`)
- Document protocol version in adapter module docstring when re-probing Goose
- Use **`set -a && . ./.env && set +a`** for Makefile targets that spawn Goose (aligned in `smoke-goose` and `make dev`)

## Related Issues

- `docs/solutions/workflow-issues/s1-phase-closeout-checklist.md` — phase closeout, AI_USAGE accuracy, review tiers
- `AI_USAGE.md` S1 entry — adversarial findings, closeout review, deferred items
- `_bmad-output/planning-artifacts/goose-spike-report.md` — spike baseline (partially superseded for conn lifecycle)
