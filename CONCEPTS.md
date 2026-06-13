# Concepts

> Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Runtime & Integration

### Agent Runtime Adapter

The abstraction boundary between Yuno and Goose. All agent execution goes through an adapter implementation (currently `AcpGooseAdapter`); the platform never calls an LLM API directly. Swapping runtimes means swapping the adapter, not rewriting orchestration.

### ACP (Agent Client Protocol)

Goose's JSON-RPC 2.0 + SSE interface exposed at `/acp` when `goose serve` runs. Session lifecycle uses connection and session routing headers; event shapes can drift between Goose versions — live smoke gate is the source of truth over spike docs.

### Smoke Gate

The Day-1 real-runtime verification (`make smoke-goose`). Starts Goose, runs one real ACP session, asserts a `tool_call` event and on-disk artifact, and saves frames for test fixtures. Required before declaring ACP integration complete; unit mocks alone are insufficient.

## Agent Execution

### Agent Task

A single-agent execution unit: one agent, one input, one Goose session. Persisted in `agent_tasks` with nullable `run_id` and `node_id` for standalone (non-workflow) runs. Status transitions: `running` → `completed` or `failed`.

### Execution Event

A persisted row in `execution_events` capturing adapter output mid-run (`tool_call`, `usage_update`) or terminal markers (`task_completed`, `task_failed`). Written via isolated DB sessions during long-running adapter calls.

### Context Preamble

The assembled system context injected as the first prompt turn: role, instructions, memory, skills. User-controlled memory/skill values are sanitized before inclusion; system prompt sanitization is a known follow-up.

## Workflow (seeded, S2+)

### Workflow Run

An orchestrated multi-agent execution against a workflow graph. Not implemented in S1 — schema and templates are seeded; orchestrator and worker are S2 scope.

### Agent Message

Persisted agent-to-agent output or feedback during a workflow run. S2 scope.

## Flagged ambiguities

- "Connection-level SSE" in the June spike meant opening GET `/acp` to obtain a conn id; Goose 1.37.0 issues conn id on sync `initialize` POST instead — the term still applies to the SSE stream used during `session/new`, not the full lifecycle.
