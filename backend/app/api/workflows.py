"""Workflow API spine — GET /workflows, POST /workflows/{id}/runs, GET /runs/{id}.

S2 Unit 3: read workflows and start a run (first pending task only). No SSE,
replay, approval, or execution endpoints yet — those are later units.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.approval_service import (
    ApprovalAlreadyResolved, ApprovalNotFound, approve_task, reject_task,
)
from app.services import workflow_service
from app.services.workflow_service import (
    WorkflowNotFound, GraphValidationError, RunNotFound, list_run_events,
)

router = APIRouter(tags=["workflows"])


class RunCreate(BaseModel):
    input: str = ""


@router.get("/workflows")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    return await workflow_service.list_workflows(db)


@router.post("/workflows/{workflow_id}/runs", status_code=201)
async def start_run(workflow_id: str, body: RunCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await workflow_service.start_run(db, workflow_id, body.input)
    except WorkflowNotFound:
        raise HTTPException(404, detail={"error": "workflow_not_found", "message": f"Workflow {workflow_id} not found"})
    except GraphValidationError as exc:
        raise HTTPException(400, detail={"error": "graph_validation_failed", "message": str(exc)})


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await workflow_service.get_run(db, run_id)
    except RunNotFound:
        raise HTTPException(404, detail={"error": "run_not_found", "message": f"Run {run_id} not found"})


@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await list_run_events(db, run_id)
    except RunNotFound:
        raise HTTPException(404, detail={"error": "run_not_found", "message": f"Run {run_id} not found"})


@router.post("/runs/{run_id}/tasks/{task_id}/approve")
async def approve_run_task(run_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await approve_task(db, run_id, task_id)
    except ApprovalNotFound:
        raise HTTPException(404, detail={"error": "approval_not_found", "message": "No pending approval for this task"})
    except ApprovalAlreadyResolved:
        raise HTTPException(409, detail={"error": "approval_already_resolved", "message": "Approval already resolved"})


@router.post("/runs/{run_id}/tasks/{task_id}/reject")
async def reject_run_task(run_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await reject_task(db, run_id, task_id)
    except ApprovalNotFound:
        raise HTTPException(404, detail={"error": "approval_not_found", "message": "No pending approval for this task"})
    except ApprovalAlreadyResolved:
        raise HTTPException(409, detail={"error": "approval_already_resolved", "message": "Approval already resolved"})
