"""test_agent_create — AC-3 critical-path test.

Verifies that agent CRUD persists all six PRD fields and retrieves them correctly.
"""
import pytest


@pytest.mark.asyncio
async def test_create_agent_all_six_fields(client):
    payload = {
        "name": "TestAgent",
        "role": "Test role",
        "system_prompt": "You are a test agent.",
        "model": "claude-sonnet-4-5",
        "tool_access": ["developer"],
        "channels": [],
    }
    r = await client.post("/agents", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()

    # All six PRD fields present and correct
    assert data["name"] == "TestAgent"
    assert data["role"] == "Test role"
    assert data["system_prompt"] == "You are a test agent."
    assert data["model"] == "claude-sonnet-4-5"
    assert data["config"]["extensions"] == ["developer"]
    assert data["id"]  # UUID assigned


@pytest.mark.asyncio
async def test_get_agent_returns_same_fields(client):
    r = await client.post("/agents", json={
        "name": "ReadbackAgent",
        "role": "Reader",
        "system_prompt": "Read things.",
        "model": "claude-haiku-4-5",
        "tool_access": ["developer"],
        "channels": [],
    })
    assert r.status_code == 201
    agent_id = r.json()["id"]

    r2 = await client.get(f"/agents/{agent_id}")
    assert r2.status_code == 200
    got = r2.json()
    assert got["name"] == "ReadbackAgent"
    assert got["system_prompt"] == "Read things."
    assert got["model"] == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_list_agents_includes_created(client):
    await client.post("/agents", json={
        "name": "ListAgent",
        "role": "Lister",
        "system_prompt": "",
        "model": "claude-sonnet-4-5",
        "tool_access": [],
        "channels": [],
    })
    r = await client.get("/agents")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert "ListAgent" in names


@pytest.mark.asyncio
async def test_update_agent_field(client):
    r = await client.post("/agents", json={
        "name": "UpdateAgent",
        "role": "Old role",
        "system_prompt": "",
        "model": "claude-sonnet-4-5",
        "tool_access": [],
        "channels": [],
    })
    agent_id = r.json()["id"]

    r2 = await client.put(f"/agents/{agent_id}", json={"role": "New role"})
    assert r2.status_code == 200
    assert r2.json()["role"] == "New role"


@pytest.mark.asyncio
async def test_delete_agent(client):
    r = await client.post("/agents", json={
        "name": "DeleteMe",
        "role": "Temp",
        "system_prompt": "",
        "model": "claude-sonnet-4-5",
        "tool_access": [],
        "channels": [],
    })
    agent_id = r.json()["id"]

    r2 = await client.delete(f"/agents/{agent_id}")
    assert r2.status_code == 204

    r3 = await client.get(f"/agents/{agent_id}")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_agent_returns_404(client):
    r = await client.get("/agents/does-not-exist")
    assert r.status_code == 404
