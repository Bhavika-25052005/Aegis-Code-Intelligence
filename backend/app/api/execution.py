import asyncio
import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.project import Project
from app.models.execution import ExecutionRun
from app.schemas.execution import ExecutionStartRequest, ExecutionStatusResponse
from app.services.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/execute", tags=["execution"])

_active_orchestrators: dict[str, bool] = {}


@router.post("", response_model=ExecutionStatusResponse)
async def start_execution(
    project_id: str,
    request: ExecutionStartRequest = ExecutionStartRequest(),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if _active_orchestrators.get(project_id):
        raise HTTPException(status_code=409, detail="Execution already running for this project")

    # Create execution run in the request session
    orchestrator = Orchestrator(project_id, db)
    execution_run = await orchestrator.create_run()

    logger.info(f"Starting execution for project {project_id}, run {execution_run.id}, {execution_run.total_tasks} tasks")

    # Mark as active and launch background task
    _active_orchestrators[project_id] = True
    asyncio.create_task(_run_orchestrator(project_id, execution_run.id))

    return execution_run


@router.post("/pause")
async def pause_execution(project_id: str):
    if not _active_orchestrators.get(project_id):
        raise HTTPException(status_code=404, detail="No active execution")
    # TODO: implement pause signal via shared state
    _active_orchestrators[project_id] = False
    return {"status": "paused"}


@router.post("/resume")
async def resume_execution(project_id: str, db: AsyncSession = Depends(get_db)):
    if _active_orchestrators.get(project_id):
        raise HTTPException(status_code=409, detail="Execution already running")

    _active_orchestrators[project_id] = True
    asyncio.create_task(_run_orchestrator(project_id, None))
    return {"status": "resumed"}


@router.post("/reset")
async def reset_execution(project_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.backlog import Feature, UserStory, Task
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id)
        .options(selectinload(Feature.user_stories).selectinload(UserStory.tasks))
    )
    features = result.scalars().all()
    reset_count = 0
    for f in features:
        f.status = "pending"
        for s in f.user_stories:
            s.status = "pending"
            for t in s.tasks:
                t.status = "pending"
                t.retry_count = 0
                t.error_message = ""
                reset_count += 1

    await db.execute(
        select(ExecutionRun).where(ExecutionRun.project_id == project_id)
    )
    # Mark old runs as cancelled
    runs = (await db.execute(
        select(ExecutionRun).where(ExecutionRun.project_id == project_id)
    )).scalars().all()
    for run in runs:
        run.status = "cancelled"

    await db.commit()
    _active_orchestrators.pop(project_id, None)
    return {"status": "reset", "tasks_reset": reset_count}


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


async def _run_orchestrator(project_id: str, run_id: str | None):
    logger.info(f"Background orchestrator starting for project {project_id}")
    try:
        async with async_session() as db:
            orchestrator = Orchestrator(project_id, db)

            # Load existing run if provided
            if run_id:
                execution_run = await db.get(ExecutionRun, run_id)
                if execution_run:
                    orchestrator.execution_run = execution_run

            await orchestrator.execute()
            logger.info(f"Background orchestrator completed for project {project_id}")
    except Exception as e:
        logger.error(f"Orchestrator failed for project {project_id}: {e}")
        logger.error(traceback.format_exc())
    finally:
        _active_orchestrators.pop(project_id, None)
