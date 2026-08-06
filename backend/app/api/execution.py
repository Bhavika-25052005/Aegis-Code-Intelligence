import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.models.execution import ExecutionRun
from app.schemas.execution import ExecutionStartRequest, ExecutionStatusResponse
from app.services.orchestrator import Orchestrator

router = APIRouter(prefix="/projects/{project_id}/execute", tags=["execution"])

_active_orchestrators: dict[str, Orchestrator] = {}


@router.post("", response_model=ExecutionStatusResponse)
async def start_execution(
    project_id: str,
    request: ExecutionStartRequest = ExecutionStartRequest(),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project_id in _active_orchestrators:
        raise HTTPException(status_code=409, detail="Execution already running for this project")

    orchestrator = Orchestrator(project_id, db)
    run = await orchestrator.create_run()
    _active_orchestrators[project_id] = orchestrator

    asyncio.create_task(_run_orchestrator(project_id, orchestrator))

    return run


@router.post("/pause")
async def pause_execution(project_id: str):
    orchestrator = _active_orchestrators.get(project_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="No active execution")
    await orchestrator.pause()
    return {"status": "paused"}


@router.post("/resume")
async def resume_execution(project_id: str, db: AsyncSession = Depends(get_db)):
    orchestrator = _active_orchestrators.get(project_id)
    if not orchestrator:
        orchestrator = Orchestrator(project_id, db)
        _active_orchestrators[project_id] = orchestrator

    asyncio.create_task(_run_orchestrator(project_id, orchestrator))
    return {"status": "resumed"}


@router.get("/status", response_model=ExecutionStatusResponse | None)
async def get_execution_status(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        return None
    return run


async def _run_orchestrator(project_id: str, orchestrator: Orchestrator):
    try:
        await orchestrator.run()
    finally:
        _active_orchestrators.pop(project_id, None)
