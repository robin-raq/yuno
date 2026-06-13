"""test_adapter — verifies AcpGooseAdapter event mapping against recorded frames.

Fixture-backed: reads data/smoke/frames.json produced by the smoke gate.
Falls back to a synthetic fixture when frames.json is not present (CI / pre-gate).
The @pytest.mark.live test exercises the real ACP server.
"""
import json
import os
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.acp_goose import AcpGooseAdapter, _parse_event, _parse_session_update, _resolve_tool_name
from app.adapters.base import TaskInput, TaskResult


FRAMES_PATH = os.path.join(
    os.path.dirname(__file__), "../../data/smoke/frames.json"
)

SYNTHETIC_FRAMES = {
    "events": [
        {"type": "tool_call", "data": {"tool": "write_file", "status": "called", "detail": {}}},
        {"type": "usage_update", "data": {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30}},
    ],
    "result": {
        "output": "I wrote the file successfully.",
        "tokens_total": 30,
        "session_id": "synthetic-session-1",
    },
}


def _load_frames() -> dict:
    if os.path.exists(FRAMES_PATH):
        with open(FRAMES_PATH) as f:
            return json.load(f)
    return SYNTHETIC_FRAMES


def test_parse_event_valid_json():
    raw = '{"method": "session/update", "params": {}}'
    parsed = _parse_event(raw)
    assert parsed == {"method": "session/update", "params": {}}


def test_parse_event_malformed_returns_none():
    assert _parse_event("not json") is None
    assert _parse_event("") is None
    assert _parse_event(None) is None


def test_parse_session_update_new_shape():
    data = {
        "method": "session/update",
        "params": {
            "sessionId": "s1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolName": "write_file",
                "status": "called",
                "parameters": {"path": "/tmp/x"},
            },
        },
    }
    update_type, update = _parse_session_update(data)
    assert update_type == "tool_call"
    assert update["toolName"] == "write_file"


def test_parse_session_update_legacy_shape():
    data = {
        "method": "session/update",
        "params": {
            "sessionUpdate": {
                "type": "usage_update",
                "usage": {"totalTokens": 42},
            }
        },
    }
    update_type, update = _parse_session_update(data)
    assert update_type == "usage_update"
    assert update["usage"]["totalTokens"] == 42


def test_frames_have_tool_call():
    frames = _load_frames()
    tool_calls = [e for e in frames["events"] if e.get("type") == "tool_call"]
    assert tool_calls, "Smoke gate frames must contain at least one tool_call event"


def test_frames_have_usage_data():
    frames = _load_frames()
    result = frames["result"]
    assert isinstance(result["tokens_total"], int)
    assert result["tokens_total"] >= 0


def test_resolve_tool_name_uses_toolName():
    assert _resolve_tool_name({"toolName": "write_file", "tool": "fallback"}) == "write_file"


def test_resolve_tool_name_falls_back_to_tool():
    assert _resolve_tool_name({"tool": "read_file"}) == "read_file"


def test_resolve_tool_name_unknown_when_absent():
    assert _resolve_tool_name({}) == "unknown"
    assert _resolve_tool_name({"status": "called"}) == "unknown"


def test_task_input_fields():
    ti = TaskInput(
        context_preamble="## Role\nTester",
        task_content="Do something",
        model="claude-sonnet-4-5",
        extensions=["developer"],
        max_turns=5,
        timeout_seconds=60,
    )
    assert ti.context_preamble.startswith("## Role")
    assert ti.extensions == ["developer"]


def test_task_result_defaults():
    tr = TaskResult(output="hello")
    assert tr.tool_calls == []
    assert tr.tokens_total == 0
    assert tr.estimated_cost == 0.0
    assert tr.session_id is None


class _FakeSSEEvent:
    def __init__(self, data: str):
        self.data = data


class _FakeStream:
    """Stateful SSE stream that resumes across multiple aiter_sse() calls via shared iterator."""

    def __init__(self, events: list):
        self._events = iter(events)

    async def _gen(self):
        for event in self._events:
            yield event

    def aiter_sse(self):
        return self._gen()


@pytest.mark.asyncio
async def test_adapter_invoke_routes_events():
    """adapter.invoke must route tool_call + usage_update through on_event and return a TaskResult."""
    conn_stream = _FakeStream([
        _FakeSSEEvent(json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"sessionId": "test-sid-123"},
        })),
    ])

    sess_stream = _FakeStream([
        _FakeSSEEvent(json.dumps({
            "method": "session/update",
            "params": {
                "sessionId": "test-sid-123",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolName": "write_file",
                    "status": "called",
                    "parameters": {"path": "/tmp/smoke.txt"},
                },
            },
        })),
        _FakeSSEEvent(json.dumps({
            "method": "session/update",
            "params": {
                "sessionId": "test-sid-123",
                "update": {
                    "sessionUpdate": "usage_update",
                    "usage": {"inputTokens": 8, "outputTokens": 22, "totalTokens": 30},
                },
            },
        })),
        _FakeSSEEvent(json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "stopReason": "end_turn",
                "usage": {"inputTokens": 8, "outputTokens": 22, "totalTokens": 30},
            },
        })),
    ])

    @asynccontextmanager
    async def fake_aconnect_sse(client, method, url, headers=None):
        if "Acp-Session-Id" in (headers or {}):
            yield sess_stream
        else:
            yield conn_stream

    init_response = MagicMock()
    init_response.raise_for_status = MagicMock()
    init_response.headers = {"acp-connection-id": "fake-conn-id"}
    init_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "1"}}

    post_response = MagicMock()
    post_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[init_response, post_response, post_response, post_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_session_client = AsyncMock()
    mock_session_client.post = AsyncMock(return_value=post_response)
    mock_session_client.__aenter__ = AsyncMock(return_value=mock_session_client)
    mock_session_client.__aexit__ = AsyncMock(return_value=False)

    task = TaskInput(
        context_preamble="## Role\nTester",
        task_content="write a test file",
        model="claude-sonnet-4-5",
        extensions=["developer"],
        max_turns=3,
        timeout_seconds=30,
    )

    received: list[dict] = []

    async def on_event(event: dict) -> None:
        received.append(event)

    with patch("app.adapters.acp_goose.aconnect_sse", side_effect=fake_aconnect_sse):
        with patch("app.adapters.acp_goose.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = [mock_client, mock_session_client]
            adapter = AcpGooseAdapter(port=9999)
            result = await adapter.invoke(task, on_event)

    tool_calls = [e for e in received if e["type"] == "tool_call"]
    usage_updates = [e for e in received if e["type"] == "usage_update"]

    assert len(tool_calls) == 1, f"Expected 1 tool_call, got {len(tool_calls)}"
    assert tool_calls[0]["data"]["tool"] == "write_file"
    assert len(usage_updates) == 1, f"Expected 1 usage_update, got {len(usage_updates)}"
    assert usage_updates[0]["data"]["totalTokens"] == 30

    assert result.session_id == "test-sid-123"
    assert result.tokens_total == 30
    assert result.estimated_cost > 0


@pytest.mark.asyncio
async def test_adapter_health_check_returns_false_without_server():
    """health_check must return False (not raise) when no Goose server is listening."""
    adapter = AcpGooseAdapter(port=9999)
    healthy = await adapter.health_check()
    assert healthy is False


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_acp_health_check():
    """Requires a running goose serve on GOOSE_PORT with ANTHROPIC_API_KEY."""
    port = int(os.getenv("GOOSE_PORT", "3284"))
    adapter = AcpGooseAdapter(port=port)
    healthy = await adapter.health_check()
    assert healthy, "Goose ACP server must be reachable for live tests"
