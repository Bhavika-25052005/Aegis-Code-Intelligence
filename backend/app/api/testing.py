import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db, async_session
from app.models.project import Project
from app.models.testing import TestRun, TestReport
from app.schemas.testing import (
    TestRunResponse, TestReportResponse,
    ManualTestRequest, ManualTestResponse,
    CustomTestRequest, CustomTestResponse,
)

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
async def get_test_runs(
    project_id: str,
    latest_only: bool = Query(default=False, description="Return only the latest execution run's test records"),
    db: AsyncSession = Depends(get_db),
):
    from app.models.execution import ExecutionRun
    from sqlalchemy import or_

    if latest_only:
        # Only return TestRuns from the single most-recent execution run + manual runs
        latest_result = await db.execute(
            select(ExecutionRun)
            .where(ExecutionRun.project_id == project_id)
            .order_by(ExecutionRun.started_at.desc())
            .limit(1)
        )
        latest_run = latest_result.scalar_one_or_none()
        conditions = [TestRun.task_id.like("manual-%")]
        if latest_run:
            conditions.append(TestRun.execution_run_id == latest_run.id)
        result = await db.execute(
            select(TestRun)
            .where(or_(*conditions))
            .order_by(TestRun.created_at.desc())
        )
    else:
        # Return all historical test runs (original behaviour)
        run_ids = await db.execute(
            select(ExecutionRun.id).where(ExecutionRun.project_id == project_id)
        )
        ids = [r[0] for r in run_ids.fetchall()]
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


@router.post("/{story_id}/custom-test", response_model=CustomTestResponse)
async def run_custom_test(
    project_id: str,
    story_id: str,
    request: CustomTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Natural-language custom test: generate, save, run and (optionally) repair."""
    from app.models.backlog import Feature, UserStory
    from app.services.test_intelligence import TestIntelligence, TestIntelligenceError
    from app.services.test_runner import TestRunnerService

    if not request.objective or not request.objective.strip():
        raise HTTPException(status_code=400, detail="objective is required")

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load story + feature
    result = await db.execute(
        select(UserStory)
        .where(UserStory.id == story_id)
        .options(selectinload(UserStory.feature), selectinload(UserStory.tasks))
    )
    user_story = result.scalar_one_or_none()
    if not user_story:
        raise HTTPException(status_code=404, detail="User story not found")

    # Approval gates
    if user_story.requirement_analysis_status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Approved Requirement Intelligence is required before running custom tests.",
        )
    if user_story.implementation_plan_status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Approved Implementation Plan is required before running custom tests.",
        )

    feature = user_story.feature

    # Resolve workspace
    workspace = project.workspace_path
    if not workspace:
        raise HTTPException(status_code=400, detail="Project workspace not configured.")

    def _load_json(val: str) -> dict:
        try:
            return json.loads(val) if val else {}
        except Exception:
            return {}

    requirement = _load_json(user_story.requirement_analysis)
    plan = _load_json(user_story.implementation_plan)

    test_intelligence = TestIntelligence(
        workspace_path=workspace,
        max_budget_usd=project.claude_max_budget_usd,
    )

    try:
        manifest = await test_intelligence.generate_custom_test(
            feature=feature,
            story=user_story,
            objective=request.objective.strip(),
            requirement=requirement,
            implementation_plan=plan,
        )
    except TestIntelligenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    detected_type = manifest.get("detected_type", "integration")
    files = manifest.get("files", [])
    test_file = files[0] if files else ""
    tests_in_manifest = manifest.get("tests", [])

    # Merge into story test_plan with source_type=user_requested
    try:
        existing: dict = json.loads(user_story.test_plan) if user_story.test_plan else {}
    except Exception:
        existing = {}
    existing_tests = existing.get("tests", [])
    existing_ids = {t.get("test_id") for t in existing_tests}
    custom_id = f"CUSTOM-{uuid.uuid4().hex[:6].upper()}"
    custom_entry = {
        "test_id": custom_id,
        "source_type": "user_requested",
        "source_text": request.objective.strip(),
        "test_type": detected_type,
        "scope": detected_type,
        "file": test_file,
        "description": request.objective.strip(),
        "status": "generated",
    }
    for entry in tests_in_manifest:
        entry["source_type"] = "user_requested"
        if entry.get("test_id") not in existing_ids:
            existing_tests.append(entry)
    if custom_id not in existing_ids:
        existing_tests.append(custom_entry)
    existing["tests"] = existing_tests
    user_story.test_plan = json.dumps(existing)
    user_story.test_updated_at = datetime.utcnow()
    await db.commit()

    # Run the custom test
    test_runner = TestRunnerService(project_id, db, workspace, project.claude_max_budget_usd)
    run_result = await asyncio.get_event_loop().run_in_executor(
        None, test_runner.run_test_files_sync, files
    )

    repair_attempts = 0
    output = run_result.raw_output

    # Repair loop (max 3) if production code violates the objective
    if not run_result.passed:
        for attempt in range(1, 4):
            repair_attempts += 1
            first_task = user_story.tasks[0] if user_story.tasks else None
            if not first_task:
                break
            repair_prompt = test_runner.prompt_builder.build_test_repair_prompt(
                task=first_task,
                user_story=user_story,
                feature=feature,
                requirement_analysis=requirement,
                implementation_plan=plan,
                failing_tests=tests_in_manifest,
                test_output=run_result.raw_output,
                attempt=attempt,
            )
            from app.services.claude_runner import ClaudeRunner
            repair_runner = ClaudeRunner(workspace, project.claude_max_budget_usd)
            await repair_runner.execute(repair_prompt)

            run_result = await asyncio.get_event_loop().run_in_executor(
                None, test_runner.run_test_files_sync, files
            )
            output = run_result.raw_output
            if run_result.passed:
                break

    final_status = "passed" if run_result.passed else (
        "needs_human_review" if repair_attempts >= 3 else "failed"
    )

    # Update test entry status in story test_plan
    try:
        existing = json.loads(user_story.test_plan) if user_story.test_plan else {}
    except Exception:
        existing = {}
    for t in existing.get("tests", []):
        if t.get("test_id") == custom_id:
            t["status"] = final_status
    user_story.test_plan = json.dumps(existing)
    user_story.test_updated_at = datetime.utcnow()
    await db.commit()

    return CustomTestResponse(
        test_id=custom_id,
        detected_type=detected_type,
        file=test_file,
        status=final_status,
        repair_attempts=repair_attempts,
        output=output[-3000:],
    )


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
