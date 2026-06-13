# Goose Technical Spike Report — Local Evidence

- **Date:** 2026-06-12 · **Machine:** this MacBook (darwin), Goose installed fresh during the spike
- **Verified version:** Goose CLI **1.37.0** via `brew install block-goose-cli`
- **Claims audited against:** `_bmad-output/planning-artifacts/prd-validation/goose-claims-ledger.md` (70 claims from the Perplexity drafts)
- **Verdict: Goose is viable — better than the drafts assumed — but the drafts' entire `goosed` REST API surface is fictional.** The real integration is the ACP (Agent Client Protocol) server (`goose serve`), recipes, and first-party scheduler/gateway subsystems.

## 1. Installation & startup — VERIFIED

| Drafts claimed | Reality (observed) |
|---|---|
| `goosed serve --port 8080` / `goosed --port 8080` ("goused") | **No `goosed` binary exists** in the CLI install. `brew install block-goose-cli` → `goose` 1.37.0 at `/usr/local/bin/goose` |
| Node 24 required by the Goose binary | False. Goose is a self-contained binary; Node is irrelevant to it |
| — | Real server: **`goose serve [--host 127.0.0.1] [--port 3284] [--with-builtin <names>]`** — "Start ACP server over HTTP and WebSocket". Starts instantly, `GET /health` → `ok` |

## 2. Programmatic interface — VERIFIED

**ACP (Agent Client Protocol), JSON-RPC 2.0, protocolVersion 1** — not a bespoke REST API.

- `POST /acp` with a JSON-RPC request → `202 Accepted` (empty body); the response arrives on the SSE stream
- `GET /acp` with `Accept: text/event-stream` → SSE stream for responses + notifications (`406` without that header)
- Same path supports WebSocket upgrade (`101 Switching Protocols` observed)
- Routing headers: server issues **`acp-connection-id`**; session-scoped calls require **`Acp-Session-Id`** header or they're rejected: `Bad Request: Acp-Session-Id header required for session-scoped methods` (observed)
- Session-scoped SSE: open a second stream with both headers — all `session/update` notifications and the prompt's final result arrive there (verified; a connection-only stream gets none of them)
- `initialize` result (observed): `loadSession: true`, `promptCapabilities: {image: true, embeddedContext: true}`, `mcpCapabilities: {http: true}`, `sessionCapabilities: {list, close}`
- Alternative headless interfaces verified: **`goose run -t/-i/--recipe --no-session --max-turns --max-tool-repetitions --system`** (executed successfully) and `goose acp` (stdio)
- `goose run --recipe spike-recipe.yaml --params task="…" --no-session` executed successfully end-to-end — the `--params` flag and recipe `parameters` substitution are both verified (the recipe-persona run quoted in §Bonus used exactly this invocation)

## 3. Authentication — VERIFIED (drafts wrong)

- **No HTTP auth on `goose serve`** (localhost binding; CORS `*`; no Bearer token, no `X-Secret-Key`, no token in any startup log — the drafts' `GOOSE_API_KEY`/`GOOSE_SECRET`/Bearer claims are all fictional for this surface)
- The only "auth" is **provider credentials**: keychain via `goose configure`, or env vars. Observed error with no key: `Configuration value not found: ANTHROPIC_API_KEY … try setting secret key(s) via environment variables`
- Provider selection via `GOOSE_PROVIDER` + `GOOSE_MODEL` env vars works (verified with `claude-code` provider; 60+ providers enumerated in the session/new response, including `anthropic`, `openai`, `ollama`)

## 4. Endpoint paths — VERIFIED

| Drafts claimed | Probe result |
|---|---|
| `POST /agent/start`, `POST /agent/resume`, `POST /reply`, `/agent/tools` | **404 — do not exist** |
| — | Real: **`/acp`** (POST JSON-RPC / GET SSE / WS), **`/health`** → `ok`, **`/status`** → `ok` |

Real methods exercised: `initialize`, `session/new`, `session/prompt`, `session/set_mode`, `session/load` (all observed working; `session/list`, `session/close` advertised in capabilities).

## 5. Streaming event format — VERIFIED (core), shapes per ACP spec

Observed on the session-scoped SSE stream during a live prompt:

- Notifications: `method: "session/update"` with `sessionUpdate` types observed: **`agent_message_chunk`** (streamed text), **`usage_update`**, `session_info_update`, `available_commands_update`
- Final result (observed): `{"result":{"stopReason":"end_turn","usage":{"totalTokens":196,"inputTokens":4,"outputTokens":192}},"id":4}` → **native token tracking for the PRD's cost requirement**
- The drafts' `content_delta` / `done {total_tokens}` schema is fictional
- `tool_call` / `tool_call_update` / `session/request_permission` are the ACP-standard remaining types — **not yet captured live** (see caveat in §6)

## 6. Tool registration & execution — VERIFIED with one critical caveat

- Real tool execution confirmed end-to-end: prompted agent ran a shell command via the `developer` builtin and the artifact file appeared on disk with correct contents (twice)
- Registration mechanisms verified: `--with-builtin <name>` on `goose serve`; `extensions:` block in recipes (`type: builtin, name: developer` validated); per-session `mcpServers` param on `session/new` (HTTP MCP capability advertised) — this is how the platform injects per-agent tools
- Bundled platform extensions enumerated via `goose info -v`: `developer` (file edit + shell), `skills`, `todo`, `analyze`, `orchestrator` (manage agent sessions: start/send/interrupt/stop), `chatrecall`, `summarize`, `apps`, `code_execution`, `tom`. **No built-in `web_search`** (drafts wrong) — web access would come via an MCP extension (e.g. fetch server)
- **CRITICAL CAVEAT:** with CLI-bridge providers (`claude-code`, `gemini-cli`, …) the tool loop runs *inside the bridged CLI subprocess*: tools execute, but **no `tool_call` events and no permission requests cross ACP, and approve mode is bypassed** (observed: approve-mode session still wrote the file with zero permission roundtrip). **The platform must use a native API provider (e.g. `anthropic` + `ANTHROPIC_API_KEY`)** so Goose owns the tool loop and emits tool events + permission requests. One live capture of `tool_call`/`request_permission` with a real key is the single remaining verification, scheduled as the first act of Story 1.

## 7. Session lifecycle — VERIFIED

- `session/new {cwd, mcpServers}` → 202; result on SSE: `sessionId` (e.g. `20260612_6`) plus **modes** and model/provider config options
- Native **session modes** (observed): `auto` (auto-approve tools), `approve` (ask before every tool call), `smart_approve`, `chat` (no tools) — switchable live via `session/set_mode` (202 accepted) → **first-party mechanism for the PRD's "interaction rules" dimension**
- `session/load` accepted for an existing session (loadSession capability true); `session/list` + `session/close` advertised
- Persistence confirmed in SQLite: `~/.local/share/goose/sessions/sessions.db` with `sessions` + `messages` tables; all spike sessions present with timestamps (note: `goose session list` CLI showed them as empty — query the DB or ACP `session/list`, don't rely on that CLI view)

## 8. Error behavior — VERIFIED

- Missing session header → HTTP 400 + plain-text reason (observed verbatim above)
- Unconfigured provider → `session/new` still succeeds; `session/prompt` → HTTP 400 (fail-fast, synchronous); CLI gives a descriptive remediation message naming the missing env var
- SSE keepalive comments (`:`) flow during idle; streams survive multi-second model latency
- Malformed JSON-RPC to `/acp` → JSON-RPC error response (initialize round-trip validated strictly)

## Bonus subsystems the drafts never mentioned (all first-party, all verified locally)

1. **`goose schedule add --schedule-id X --cron '0 3 * * *' --recipe-source recipe.yaml`** — native cron scheduler; add/list/remove/run-now/sessions all exercised (job created, listed as IDLE, removed). Direct fit for the PRD "Schedules" dimension.
2. **`goose gateway start --bot-token <TOKEN> telegram`** — native Telegram gateway (status/start/stop/pair verified as commands; full test needs a bot token). Candidate for the PRD external-channel requirement, with the platform's own python-telegram-bot integration as the controlled alternative.
3. **Recipes** — YAML agent definitions (`version/title/description/instructions/prompt/parameters/extensions/settings{goose_provider, goose_model}`); `goose recipe validate` passed; a recipe-defined persona observably shaped a live run's voice. **This is the per-agent configuration unit** (system prompt + tools + model per agent).
4. **Native usage reporting** per turn (tokens in/out/total) — feeds the PRD's token/cost tracking.

## Decision input

Goose **confirmed** as the runtime, on real grounds: ACP server with sessions/modes/streaming, recipes for per-agent config, native scheduler, native usage metrics, first-party Telegram gateway, MCP extension ecosystem — at the cost of integrating against ACP (JSON-RPC + SSE headers) rather than the drafts' imagined REST. Compliant fallback inside the same runtime: `goose run --recipe` subprocess per workflow node (verified working today, zero protocol risk). The non-compliant DirectLLM/LangChain fallbacks are deleted.

**Prerequisites the user must supply on Day 1:** an `ANTHROPIC_API_KEY` (or other native-provider key) in `.env`, and a Telegram bot token from @BotFather.
