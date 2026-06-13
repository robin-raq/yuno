"""Agent CRUD endpoints — POST/GET/PUT/DELETE /agents."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentCreate(BaseModel):
    name: str
    role: str
    system_prompt: str = ""
    model: str
    tool_access: list[str] = ["developer"]
    channels: list[str] = []


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    status: str | None = None


@router.get("")
async def list_agents(db: AsyncSession = Depends(get_db)):
    return await agent_service.list_agents(db)


@router.post("", status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    return await agent_service.create_agent(db, body.model_dump())


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)):
    agent = await agent_service.update_agent(db, agent_id, body.model_dump(exclude_none=True))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await agent_service.delete_agent(db, agent_id)
    if not deleted:
        raise HTTPException(404, "Agent not found")
