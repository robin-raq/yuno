"""Agent task execution endpoints — POST /agents/{id}/tasks, GET task + events."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.services import task_service

router = APIRouter(prefix="/agents", tags=["tasks"])


class TaskSubmit(BaseModel):
    input: str


@router.post("/{agent_id}/tasks", status_code=201)
async def submit_task(
    agent_id: str,
    body: TaskSubmit,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await task_service.submit_task(db, agent_id, body.input)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Task execution failed: {exc}")


@router.get("/{agent_id}/tasks/{task_id}")
async def get_task(agent_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    task = await task_service.get_task_with_events(db, task_id)
    if not task or task["agent_id"] != agent_id:
        raise HTTPException(404, "Task not found")
    return task
