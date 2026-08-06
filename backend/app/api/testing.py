import asyncio
import logging
import traceback
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.project import Project
from app.models.testing import TestRun, TestReport
from app.schemas.testing import TestRunResponse, TestReportResponse, ManualTestRequest, ManualTestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/tests", tags=["testing"])

_active_manual_tests: dict[str, str] = {}


@router.post("/trigger", response_model=ManualTestResponse)
async def trigger_manual_test(
    project_id: str,
    request: ManualTestRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.workspace_path:
        raise HTTPException(status_code=400, detail="Project has no workspace path configured")

    if not project.is_repo_cloned:
        raise HTTPException(status_code=400, detail="Repository not cloned yet. Please configure GitHub and clone first.")

    if project_id in _active_manual_tests:
        raise HTTPException(status_code=409, detail="A manual test is already running for this project")

    if request.scope not in ("regression", "pr"):
        raise HTTPException(status_code=400, detail="scope must be 'regression' or 'pr'")

    test_run_id = str(uuid.uuid4())
    _active_manual_tests[project_id] = test_run_id

    asyncio.create_task(_run_manual_tests(project_id, test_run_id, request.scope, request.branch, request.test_types))

    return ManualTestResponse(test_run_id=test_run_id, status="started")


@router.get("/active")
async def get_active_test(project_id: str):
    if project_id in _active_manual_tests:
        return {"active": True, "test_run_id": _active_manual_tests[project_id]}
    return {"active": False, "test_run_id": None}


@router.get("/runs", response_model=list[TestRunResponse])
async def get_test_runs(project_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.execution import ExecutionRun

    # Get runs from execution-based tests
    run_ids = await db.execute(
        select(ExecutionRun.id).where(ExecutionRun.project_id == project_id)
    )
    ids = [r[0] for r in run_ids.fetchall()]

    # Get all test runs: both execution-linked and manual (execution_run_id is NULL)
    from sqlalchemy import or_
    conditions = [TestRun.task_id.like("manual-%")]
    if ids:
        conditions.append(TestRun.execution_run_id.in_(ids))

    result = await db.execute(
        select(TestRun)
        .where(or_(*conditions))
        .order_by(TestRun.created_at.desc())
    )
    return result.scalars().all()


@router.get("/reports", response_model=list[TestReportResponse])
async def get_test_reports(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TestReport)
        .where(TestReport.project_id == project_id)
        .order_by(TestReport.created_at.desc())
    )
    return result.scalars().all()


@router.get("/latest-report", response_model=TestReportResponse | None)
async def get_latest_report(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TestReport)
        .where(TestReport.project_id == project_id)
        .order_by(TestReport.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _run_manual_tests(project_id: str, test_run_id: str, scope: str, branch: str | None, test_types: list[str]):
    from app.services.manual_test_runner import ManualTestService

    logger.info(f"Manual test background task starting: project={project_id}, scope={scope}")
    try:
        async with async_session() as db:
            project = await db.get(Project, project_id)
            if not project:
                logger.error(f"Project {project_id} not found in background task")
                return

            service = ManualTestService(project, db)
            await service.run(scope, branch, test_types)
            logger.info(f"Manual test completed for project {project_id}")
    except Exception as e:
        logger.error(f"Manual test failed for project {project_id}: {e}")
        logger.error(traceback.format_exc())
    finally:
        _active_manual_tests.pop(project_id, None)
