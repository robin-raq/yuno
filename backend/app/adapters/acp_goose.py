"""AcpGooseAdapter — JSON-RPC 2.0 + SSE over the Goose ACP server.

Verified against Goose 1.37.0 (2026-06-13 re-probe). Protocol deltas from the
June spike:
  - initialize is synchronous on POST /acp (conn id returned in response header)
  - connection/session routing uses Acp-Connection-Id / Acp-Session-Id headers
  - session/prompt params: {sessionId, prompt: [{type: "text", text: "..."}]}
  - session/update payloads nest under params.update with sessionUpdate as a string
"""
import asyncio
import itertools
import json
import logging
import os
from typing import Awaitable, Callable

import httpx
from httpx_sse import aconnect_sse

from app.adapters.base import AgentRuntimeAdapter, TaskInput, TaskResult

log = logging.getLogger(__name__)

_COST_PER_1K = {
    "claude-sonnet-4-5": 0.003,
    "claude-opus-4-8": 0.015,
    "claude-haiku-4-5": 0.00025,
}
_DEFAULT_COST = 0.003


def _conn_headers(conn_id: str) -> dict[str, str]:
    return {"Acp-Connection-Id": conn_id}


def _session_headers(conn_id: str, session_id: str) -> dict[str, str]:
    return {
        "Acp-Connection-Id": conn_id,
        "Acp-Session-Id": session_id,
    }


def _parse_session_update(data: dict) -> tuple[str | None, dict]:
    """Return (update_type, update_body) for old and new ACP session/update shapes."""
    params = data.get("params", {})
    update = params.get("update")
    if isinstance(update, dict) and update.get("sessionUpdate"):
        update_type = update.get("sessionUpdate")
        if isinstance(update_type, str):
            return update_type, update
        if isinstance(update_type, dict):
            merged = {**update_type, **update}
            merged.pop("sessionUpdate", None)
            return update_type.get("type"), merged

    legacy = params.get("sessionUpdate", {})
    if isinstance(legacy, dict):
        return legacy.get("type"), legacy
    return None, {}


class AcpGooseAdapter(AgentRuntimeAdapter):
    def __init__(self, host: str = "127.0.0.1", port: int = 3284) -> None:
        self._base = f"http://{host}:{port}"
        self._acp = f"{self._base}/acp"
        self._id_counter = itertools.count(1)

    def _next_id(self) -> int:
        return next(self._id_counter)

    def _rpc(self, method: str, params: dict) -> tuple[dict, int]:
        rpc_id = self._next_id()
        return {"jsonrpc": "2.0", "method": method, "params": params, "id": rpc_id}, rpc_id

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self._base}/health")
                return r.status_code == 200
        except Exception:
            return False

    async def invoke(
        self,
        task: TaskInput,
        on_event: Callable[[dict], Awaitable[None]],
    ) -> TaskResult:
        full_prompt = f"{task.context_preamble}\n\n---\n## Task\n{task.task_content}"

        async with httpx.AsyncClient(timeout=60) as client:
            conn_id: str | None = None
            session_id: str | None = None

            try:
                init_payload, init_id = self._rpc("initialize", {
                    "protocolVersion": "1",
                    "clientInfo": {"name": "yuno", "version": "0.1.0"},
                })
                init_resp = await client.post(self._acp, json=init_payload)
                init_resp.raise_for_status()
                conn_id = init_resp.headers.get("acp-connection-id")
                if not conn_id:
                    raise RuntimeError("Goose did not return acp-connection-id header on initialize")

                init_body = init_resp.json()
                if init_body.get("id") == init_id and "error" in init_body:
                    raise RuntimeError(f"initialize failed: {init_body['error']}")

                session_payload, session_rpc_id = self._rpc("session/new", {
                    "cwd": os.getcwd(),
                    # Goose builtins (e.g. "developer") are loaded at server startup via
                    # --with-builtin. Per-session MCP server injection is deferred until
                    # agent schemas carry explicit server configs (S4+).
                    "mcpServers": [],
                })
                async with aconnect_sse(
                    client,
                    "GET",
                    self._acp,
                    headers={**_conn_headers(conn_id), "Accept": "text/event-stream"},
                ) as conn_stream:
                    r = await client.post(
                        self._acp,
                        json=session_payload,
                        headers=_conn_headers(conn_id),
                    )
                    r.raise_for_status()
                    async for event in conn_stream.aiter_sse():
                        data = _parse_event(event.data)
                        if data and data.get("id") == session_rpc_id and "result" in data:
                            session_id = data["result"]["sessionId"]
                            log.debug("ACP session: %s", session_id)
                            break
                        if data and "error" in data and data.get("id") == session_rpc_id:
                            raise RuntimeError(f"session/new failed: {data['error']}")

                if not session_id:
                    raise RuntimeError("session/new did not return a sessionId")

                result = await self._run_prompt(
                    conn_id,
                    session_id,
                    full_prompt,
                    on_event,
                    task,
                )
            finally:
                if session_id and conn_id:
                    await self._close_session(client, conn_id, session_id)

        return result

    async def _run_prompt(
        self,
        conn_id: str,
        session_id: str,
        prompt: str,
        on_event: Callable[[dict], Awaitable[None]],
        task: TaskInput,
    ) -> TaskResult:
        prompt_payload, prompt_id = self._rpc("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": prompt}],
        })

        output_chunks: list[str] = []
        tool_calls: list[dict] = []
        tokens_input = 0
        tokens_output = 0
        tokens_total = 0

        async with httpx.AsyncClient(timeout=task.timeout_seconds) as session_client:
            session_headers = {
                **_session_headers(conn_id, session_id),
                "Accept": "text/event-stream",
            }
            async with aconnect_sse(
                session_client, "GET", self._acp, headers=session_headers
            ) as sess_stream:
                r = await session_client.post(
                    self._acp,
                    json=prompt_payload,
                    headers=_session_headers(conn_id, session_id),
                )
                r.raise_for_status()

                async for event in sess_stream.aiter_sse():
                    if not event.data or not event.data.strip():
                        continue
                    data = _parse_event(event.data)
                    if not data:
                        continue

                    if data.get("id") == prompt_id and "result" in data:
                        usage = data["result"].get("usage", {})
                        tokens_input = usage.get("inputTokens", tokens_input)
                        tokens_output = usage.get("outputTokens", tokens_output)
                        tokens_total = usage.get("totalTokens", tokens_total or tokens_input + tokens_output)
                        break

                    if data.get("id") == prompt_id and "error" in data:
                        raise RuntimeError(f"session/prompt failed: {data['error']}")

                    if data.get("method") != "session/update":
                        continue

                    update_type, update = _parse_session_update(data)

                    if update_type == "agent_message_chunk":
                        content = update.get("content", "")
                        if isinstance(content, dict):
                            output_chunks.append(content.get("text", ""))
                        elif isinstance(content, str):
                            output_chunks.append(content)

                    elif update_type in ("tool_call", "tool_call_update"):
                        tc = {
                            "tool": _resolve_tool_name(update),
                            "status": update.get("status", "called"),
                            "detail": update.get("parameters", update.get("detail", {})),
                        }
                        tool_calls.append(tc)
                        await on_event({"type": "tool_call", "data": tc})

                    elif update_type == "usage_update":
                        usage = update.get("usage", {})
                        if usage:
                            tokens_input = usage.get("inputTokens", tokens_input)
                            tokens_output = usage.get("outputTokens", tokens_output)
                            tokens_total = usage.get("totalTokens", tokens_total)
                            await on_event({"type": "usage_update", "data": usage})

                    elif "error" in data:
                        raise RuntimeError(f"ACP error: {data['error']}")

        cost_per_1k = _COST_PER_1K.get(task.model, _DEFAULT_COST)
        estimated_cost = (tokens_total / 1000) * cost_per_1k

        return TaskResult(
            output="".join(output_chunks),
            tool_calls=tool_calls,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_total=tokens_total,
            estimated_cost=estimated_cost,
            session_id=session_id,
        )

    async def _close_session(
        self, client: httpx.AsyncClient, conn_id: str, session_id: str
    ) -> None:
        try:
            close_payload, _ = self._rpc("session/close", {"sessionId": session_id})
            await client.post(
                self._acp,
                json=close_payload,
                headers=_session_headers(conn_id, session_id),
                timeout=5,
            )
        except Exception as exc:
            log.warning("session/close failed (non-fatal): %s", exc)


def _resolve_tool_name(update: dict) -> str:
    """Return the tool name from a tool_call update, warning when it cannot be determined."""
    name = update.get("toolName", update.get("tool", "unknown"))
    if name == "unknown":
        log.warning("ACP tool_call missing toolName/tool field; keys=%s", list(update.keys()))
    return name


def _parse_event(data: str) -> dict | None:
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None
