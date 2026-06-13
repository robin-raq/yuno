"""Workflow API spine — GET /workflows, POST /workflows/{id}/runs, GET /runs/{id}.

S2 Unit 3: read workflows and start a run (first pending task only). No SSE,
replay, approval, or execution endpoints yet — those are later units.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import workflow_service
from app.services.workflow_service import (
    WorkflowNotFound, GraphValidationError, RunNotFound,
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
