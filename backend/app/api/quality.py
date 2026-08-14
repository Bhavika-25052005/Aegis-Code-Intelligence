"""
Quality Traceability + Delivery API.

Endpoints:
  GET  /projects/{project_id}/quality/{story_id}                 - full quality data
  GET  /projects/{project_id}/quality/{story_id}/run-history     - execution run history
  GET  /projects/{project_id}/quality/{story_id}/report.pdf      - filtered PDF
  POST /projects/{project_id}/quality/{story_id}/verify-traceability
  POST /projects/{project_id}/quality/{story_id}/update-readme
  POST /projects/{project_id}/quality/{story_id}/push
"""

import json
import logging
import os
import pathlib
import re
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.backlog import Feature, UserStory
from app.models.execution import ExecutionRun
from app.models.project import Project
from app.models.testing import TestRun
from app.services.crypto import decrypt_value, encrypt_value
from app.services.quality_reporter import QualityReporter
from app.services.code_quality import CodeQualityService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/quality", tags=["quality"])
reporter = QualityReporter()
_quality_svc = CodeQualityService()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_story_context(project_id: str, story_id: str, db: AsyncSession):
    """Load project, story, and feature together."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(UserStory)
        .where(UserStory.id == story_id)
        .options(selectinload(UserStory.feature), selectinload(UserStory.tasks))
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="User story not found")

    feature = story.feature
    return project, story, feature


def _load_json(val: str) -> dict:
    try:
        return json.loads(val) if val else {}
    except Exception:
        return {}


def _summary_from_test_runs(test_runs: list, test_plan_json: str = "") -> dict:
    """Build test summary from latest-run TestRun records + custom tests from test_plan.

    Custom tests are run via the custom-test API and never create TestRun records;
    they live only in story.test_plan with source_type='user_requested'.
    Using TestRun records for unit/integration/regression prevents historical
    accumulation from inflating the counts across multiple execution runs.
    """
    unit = sum(r.total_tests for r in test_runs if r.test_type == "unit")
    integ_sys = sum(
        r.total_tests for r in test_runs
        if r.test_type in ("integration", "system", "quality")
    )
    regression = sum(r.total_tests for r in test_runs if r.test_type == "regression")
    passed = sum(r.passed_tests for r in test_runs)
    failed = sum(r.failed_tests for r in test_runs)

    # Custom tests have no TestRun records - read from test_plan
    custom = 0
    custom_passed = 0
    try:
        tests = json.loads(test_plan_json).get("tests", []) if test_plan_json else []
        custom_tests = [t for t in tests if t.get("source_type") == "user_requested"]
        custom = len(custom_tests)
        custom_passed = sum(1 for t in custom_tests if t.get("status") == "passed")
    except Exception:
        pass

    return {
        "unit": unit,
        "integration_system": integ_sys,
        "integration": integ_sys,
        "system": 0,
        "regression": regression,
        "custom": custom,
        "total": unit + integ_sys + regression + custom,
        "passed": passed + custom_passed,
        "failed": failed + (custom - custom_passed),
    }


def _build_test_run_summary(test_runs: list, test_plan_json: str = "") -> dict:
    """Snapshot-friendly summary of the latest run for use in release readiness.
    Stored inside the quality snapshot so readiness checks never read historical test_plan.
    """
    unit_failed = sum(r.failed_tests for r in test_runs if r.test_type == "unit")
    integ_failed = sum(
        r.failed_tests for r in test_runs
        if r.test_type in ("integration", "system", "quality")
    )
    reg_failed = sum(r.failed_tests for r in test_runs if r.test_type == "regression")

    custom_count = 0
    custom_failed = 0
    try:
        tests = json.loads(test_plan_json).get("tests", []) if test_plan_json else []
        custom_tests = [t for t in tests if t.get("source_type") == "user_requested"]
        custom_count = len(custom_tests)
        custom_failed = sum(1 for t in custom_tests if t.get("status") not in ("passed",))
    except Exception:
        pass

    return {
        "has_data": bool(test_runs),
        "unit_failed": unit_failed,
        "integ_failed": integ_failed,
        "reg_failed": reg_failed,
        "custom_count": custom_count,
        "custom_failed": custom_failed,
    }


def _push_gate_check(story, code_quality_snapshot: dict | None = None) -> str | None:
    """Return blocking reason string or None if push is allowed."""
    if story.requirement_analysis_status != "approved":
        return "Requirement analysis is not approved"
    if story.implementation_plan_status != "approved":
        return "Implementation plan is not approved"
    if story.status != "completed":
        all_done = all(t.status == "completed" for t in story.tasks)
        if not all_done:
            return "Not all story tasks are completed"
    if story.test_status not in ("passed",):
        return f"Quality gate has not passed (current status: {story.test_status})"
    # Day 5: require release readiness
    if code_quality_snapshot is None:
        return "Run Quality Analysis first to enable push"
    readiness = code_quality_snapshot.get("release_readiness", {})
    if readiness.get("is_stale"):
        return "Quality analysis is stale - refresh before pushing"
    if readiness.get("status") != "ready":
        blockers = readiness.get("blockers", [])
        if blockers:
            return f"Not release ready: {blockers[0]['message']}"
        return "Release readiness checks not passed"
    return None


# ── GET quality data ──────────────────────────────────────────────────────────

@router.get("/{story_id}")
async def get_quality(
    project_id: str,
    story_id: str,
    search: str | None = Query(default=None),
    criterion: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    project, story, feature = await _get_story_context(project_id, story_id, db)
    requirement = _load_json(story.requirement_analysis)

    # ── Fetch TestRun records from the LATEST completed execution run only ──
    # Using all runs would inflate counts when there are multiple run history entries.
    latest_run_result = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.started_at.desc())
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()
    test_runs = []
    if latest_run:
        tr_result = await db.execute(
            select(TestRun).where(TestRun.execution_run_id == latest_run.id)
        )
        test_runs = tr_result.scalars().all()

    # Build AC legend
    ac_criteria = requirement.get("acceptance_criteria", [])
    ac_legend = [
        {"id": f"AC{i+1}", "text": c.strip(), "color": _ac_color_hex(i)}
        for i, c in enumerate(ac_criteria)
    ]

    # Build/restore traceability snapshot (cached - only recomputes when test_plan changes)
    traceability_data = await reporter.ensure_traceability(
        story, requirement, project.workspace_path or "", test_runs=test_runs
    )
    # Persist snapshot and any mapping changes
    await db.commit()

    traceability = {"tests": traceability_data["tests"]}
    # Use TestRun records from the LATEST run + custom tests from test_plan.
    # This prevents inflated counts from accumulated test_plan history.
    summary = _summary_from_test_runs(test_runs, story.test_plan or "") if test_runs else traceability_data["summary"]

    # Filter
    filtered = reporter.filter_tests(
        traceability,
        search=search,
        criterion=criterion,
        test_type=type,
        status=status,
    )

    # Paginate
    total_filtered = len(filtered)
    start = (page - 1) * page_size
    page_tests = filtered[start : start + page_size]

    # Day 5: load code quality snapshot and check staleness
    cq_raw = story.code_quality_snapshot or ""
    code_quality = _load_json(cq_raw)
    quality_stale = False
    release_readiness: dict = {}
    if code_quality:
        workspace = project.workspace_path or ""
        saved_fp = code_quality.get("workspace_fingerprint", "")
        if saved_fp:
            current_fp = _quality_svc.workspace_fingerprint(workspace)
            quality_stale = saved_fp != current_fp
        if quality_stale and "release_readiness" in code_quality:
            code_quality["release_readiness"]["is_stale"] = True
        release_readiness = code_quality.get("release_readiness", {})

    # Push gate (now Day 5-gated)
    push_blocked_reason = _push_gate_check(story, code_quality if code_quality else None)

    # README status - check if workspace has README.md
    readme_status = "unknown"
    if project.workspace_path:
        import pathlib
        readme_path = pathlib.Path(project.workspace_path) / "README.md"
        readme_status = "present" if readme_path.exists() else "missing"

    # Repo delivery status
    repo_configured = bool(project.github_repo_url and project.github_pat_encrypted)

    return {
        "project": {"id": project.id, "name": project.name},
        "feature": {"id": feature.id, "title": feature.title} if feature else None,
        "story": {"id": story.id, "title": story.title, "test_status": story.test_status},
        "quality_gate": story.test_status,
        "test_summary": summary,
        "ac_legend": ac_legend,
        "tests": page_tests,
        "total_filtered": total_filtered,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total_filtered + page_size - 1) // page_size),
        "readme_status": readme_status,
        "repo_configured": repo_configured,
        "push_blocked_reason": push_blocked_reason,
        # Day 5 additions
        "code_quality": code_quality,
        "quality_stale": quality_stale,
        "release_readiness": release_readiness,
    }


# ── GET run history ──────────────────────────────────────────────────────────

@router.get("/{story_id}/run-history")
async def get_run_history(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return all ExecutionRuns for this project, each with their aggregated
    TestRun totals and per-type breakdown. Ordered newest first.
    """
    # All execution runs for the project
    ex_result = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.started_at.desc())
    )
    execution_runs = ex_result.scalars().all()

    if not execution_runs:
        return {"runs": []}

    run_ids = [r.id for r in execution_runs]

    # All TestRun records for these execution runs
    tr_result = await db.execute(
        select(TestRun)
        .where(TestRun.execution_run_id.in_(run_ids))
        .order_by(TestRun.created_at)
    )
    all_test_runs = tr_result.scalars().all()

    # Group TestRuns by execution_run_id
    grouped: dict[str, list] = {r.id: [] for r in execution_runs}
    for tr in all_test_runs:
        if tr.execution_run_id in grouped:
            grouped[tr.execution_run_id].append(tr)

    runs_out = []
    for ex in execution_runs:
        test_runs = grouped[ex.id]

        # Aggregate totals
        total = sum(r.total_tests for r in test_runs)
        passed = sum(r.passed_tests for r in test_runs)
        failed = sum(r.failed_tests for r in test_runs)

        # Per-type breakdown
        by_type: dict[str, dict] = {}
        for tr in test_runs:
            t = tr.test_type
            if t not in by_type:
                by_type[t] = {"type": t, "total": 0, "passed": 0, "failed": 0,
                               "fix_attempts": 0, "error_summary": ""}
            by_type[t]["total"] += tr.total_tests
            by_type[t]["passed"] += tr.passed_tests
            by_type[t]["failed"] += tr.failed_tests
            if tr.fix_attempt > 0:
                by_type[t]["fix_attempts"] += 1
            if tr.error_summary and not by_type[t]["error_summary"]:
                by_type[t]["error_summary"] = tr.error_summary[:300]

        runs_out.append({
            "execution_run_id": ex.id,
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            "total_tasks": ex.total_tasks,
            "completed_tasks": ex.completed_tasks,
            "failed_tasks": ex.failed_tasks,
            "total_tests": total,
            "passed_tests": passed,
            "failed_tests": failed,
            "by_type": list(by_type.values()),
        })

    return {"runs": runs_out}


# ── GET PDF ───────────────────────────────────────────────────────────────────

@router.get("/{story_id}/report.pdf")
async def download_report_pdf(
    project_id: str,
    story_id: str,
    search: str | None = Query(default=None),
    criterion: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    project, story, feature = await _get_story_context(project_id, story_id, db)
    requirement = _load_json(story.requirement_analysis)

    # Use cached snapshot if available so PDF has same data as the UI
    cached = reporter.load_snapshot(story, reporter.compute_snapshot_hash(story))
    if cached:
        traceability = {"tests": cached["tests"]}
    else:
        test_plan = _load_json(story.test_plan)
        traceability = {"tests": test_plan.get("tests", [])}

    filtered = reporter.filter_tests(
        traceability,
        search=search,
        criterion=criterion,
        test_type=type,
        status=status,
    )

    active_filters = {
        "criterion": criterion,
        "type": type,
        "status": status,
        "search": search,
    }

    # Write to a temp file - FastAPI FileResponse handles cleanup
    suffix = f"-{story.title[:20].replace(' ', '_')}.pdf"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()

    reporter.generate_pdf(
        project=project,
        feature=feature,
        story=story,
        requirement=requirement,
        tests=filtered,
        active_filters=active_filters,
        output_path=tmp.name,
    )

    safe_title = re.sub(r"[^\w\-]", "_", story.title[:30])
    filename = f"aegis-traceability-{safe_title}.pdf"

    return FileResponse(
        path=tmp.name,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── POST verify traceability (Claude once) ────────────────────────────────────

@router.post("/{story_id}/verify-traceability")
async def verify_traceability(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, story, feature = await _get_story_context(project_id, story_id, db)
    requirement = _load_json(story.requirement_analysis)

    # Fetch TestRun records from latest run only
    latest_run_result = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.started_at.desc())
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()
    test_runs = []
    if latest_run:
        tr_result = await db.execute(select(TestRun).where(TestRun.execution_run_id == latest_run.id))
        test_runs = tr_result.scalars().all()

    workspace = project.workspace_path or ""
    # Use Claude-enhanced version which inspects test files for remaining unmapped tests
    traceability = await reporter.ensure_traceability_with_claude(
        story, requirement, workspace, test_runs=test_runs
    )

    # Persist updated test_plan and invalidated cache
    await db.commit()

    mapped = sum(1 for t in traceability["tests"] if t.get("criteria"))
    unmapped = sum(1 for t in traceability["tests"] if not t.get("criteria"))

    return {
        "status": "ok",
        "ac_legend": traceability.get("ac_legend", []),
        "tests": traceability["tests"],
        "total": len(traceability["tests"]),
        "mapped": mapped,
        "unmapped": unmapped,
    }


# ── POST update README ────────────────────────────────────────────────────────

@router.post("/{story_id}/update-readme")
async def update_readme(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, story, feature = await _get_story_context(project_id, story_id, db)

    workspace = project.workspace_path
    if not workspace:
        raise HTTPException(status_code=400, detail="Project has no workspace configured")

    requirement = _load_json(story.requirement_analysis)
    plan = _load_json(story.implementation_plan)
    summary = reporter.build_summary(story)

    completed_tasks = [t.title for t in story.tasks if t.status == "completed"]
    req_summary = requirement.get("summary", story.title)
    work_summary = plan.get("work_summary", "")

    prompt = f"""Inspect this completed project and its existing README.md if present.

Use:
- Current repository code
- Approved requirement summary: {req_summary}
- Work summary: {work_summary}
- Completed tasks: {json.dumps(completed_tasks)}
- Test summary: unit={summary['unit']}, integration={summary['integration']}, \
system={summary['system']}, regression={summary['regression']}, \
custom={summary['custom']}, total={summary['total']}, \
passed={summary['passed']}, failed={summary['failed']}

If README.md does not exist: create a concise useful README.md.
If README.md exists: preserve good existing content and minimally update it.

Ensure useful sections where applicable:
- Project Overview
- Setup / Installation
- Run Instructions
- Implemented Features
- Testing
- Recent Changes

Do not add fabricated commands, dependencies or claims.
Do not replace a good README unnecessarily.
Do not commit or push.
"""

    from app.services.claude_runner import ClaudeRunner
    runner = ClaudeRunner(
        workspace_path=workspace,
        max_budget_usd=1.0,
        allowed_tools="Read,Write,Edit,Glob",
    )
    result = await runner.execute(prompt)

    if not result.success:
        raise HTTPException(status_code=500, detail=f"README update failed: {result.error[:300]}")

    # Refresh repository metadata so README is visible to Git
    try:
        from app.services.repository_intelligence import RepositoryIntelligence
        from app.models.project import Project as ProjectModel
        repo_intel = RepositoryIntelligence(
            project=project, db=db, workspace_path=workspace
        )
        await repo_intel.refresh_after_task(["README.md"])
    except Exception as exc:
        logger.warning("Repository metadata refresh after README update failed: %s", exc)

    import pathlib
    readme_exists = (pathlib.Path(workspace) / "README.md").exists()
    return {"status": "ok", "readme_present": readme_exists, "output": result.output[:500]}


# ── POST analyze (Day 5) ─────────────────────────────────────────────────────

@router.post("/{story_id}/analyze")
async def analyze_quality(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run Day 5 quality analysis: coverage + Claude code review + scores + release readiness."""
    from app.services.websocket_manager import manager as ws_manager

    project, story, feature = await _get_story_context(project_id, story_id, db)
    workspace = project.workspace_path or ""

    async def broadcast(step: str, message: str):
        await ws_manager.broadcast(project_id, {
            "type": "quality_progress",
            "payload": {"step": step, "message": message, "story_id": story_id},
        })

    await broadcast("started", "Quality analysis started…")

    # Fetch latest TestRun records once - used for summary + readiness checks
    latest_run_result = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.started_at.desc())
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()
    latest_test_runs = []
    if latest_run:
        tr_result = await db.execute(
            select(TestRun).where(TestRun.execution_run_id == latest_run.id)
        )
        latest_test_runs = list(tr_result.scalars().all())

    # 1. Coverage
    await broadcast("coverage", "Running coverage analysis…")
    try:
        coverage = await _quality_svc.run_coverage(project, story, workspace)
    except Exception as exc:
        logger.warning("Coverage run error: %s", exc)
        coverage = {"status": "error", "reason": str(exc)[:200], "tool": None}
    await broadcast("coverage_done", f"Coverage: {coverage.get('status')} {coverage.get('overall', '') or ''}")

    # 2. Claude code review
    await broadcast("review", "Running Claude code review (read-only)…")
    try:
        review = await _quality_svc.run_code_review(project, story, workspace, coverage)
    except Exception as exc:
        logger.warning("Code review error: %s", exc)
        review = {
            "status": "error",
            "findings": [],
            "scores": _quality_svc.calculate_review_scores([]),
            "summary": f"Review error: {str(exc)[:200]}",
        }
    n_findings = len(review.get("findings", []))
    await broadcast("review_done", f"Review complete: {n_findings} finding(s)")

    # 3. Build and persist snapshot (include test_run_summary for readiness checks)
    fingerprint = _quality_svc.workspace_fingerprint(workspace)
    snapshot: dict = {
        "coverage": coverage,
        "review": review,
        "test_run_summary": _build_test_run_summary(latest_test_runs, story.test_plan or ""),
        "generated_at": datetime.utcnow().isoformat(),
        "workspace_fingerprint": fingerprint,
    }

    # 4. Release readiness (uses test_run_summary - not accumulated test_plan history)
    await broadcast("readiness", "Calculating release readiness…")
    readiness = _quality_svc.calculate_release_readiness(project, story, snapshot)
    snapshot["release_readiness"] = readiness

    # 5. Persist
    story.code_quality_snapshot = json.dumps(snapshot)
    await db.commit()
    await db.refresh(story)

    await broadcast("complete", f"Analysis complete - {'RELEASE READY' if readiness['status'] == 'ready' else 'NOT READY'}")

    return {
        "status": "ok",
        "coverage": coverage,
        "review": {
            "findings": review.get("findings", []),
            "scores": review.get("scores", {}),
            "summary": review.get("summary", ""),
        },
        "release_readiness": readiness,
        "workspace_fingerprint": fingerprint,
        "generated_at": snapshot["generated_at"],
    }


# ── GET findings (filtered) ───────────────────────────────────────────────────

@router.get("/{story_id}/findings")
async def get_findings(
    project_id: str,
    story_id: str,
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    file: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return filtered code review findings from persisted snapshot."""
    _, story, _ = await _get_story_context(project_id, story_id, db)
    cq = _load_json(story.code_quality_snapshot or "")
    findings: list[dict] = cq.get("review", {}).get("findings", [])

    # Apply filters
    if search:
        s = search.lower()
        findings = [
            f for f in findings
            if s in f.get("finding", "").lower()
            or s in f.get("file", "").lower()
            or s in f.get("recommendation", "").lower()
        ]
    if severity:
        findings = [f for f in findings if f.get("severity") == severity.lower()]
    if category:
        findings = [f for f in findings if f.get("category") == category.lower()]
    if file:
        findings = [f for f in findings if file.lower() in f.get("file", "").lower()]

    counts = {sev: sum(1 for f in cq.get("review", {}).get("findings", []) if f.get("severity") == sev)
              for sev in ("critical", "high", "medium", "low")}

    return {"findings": findings, "total": len(findings), "counts": counts}


# ── POST push to repo ─────────────────────────────────────────────────────────

class PushRequest(BaseModel):
    repo_url: str | None = None
    pat: str | None = None
    commit_message: str | None = None


@router.post("/{story_id}/push")
async def push_to_repo(
    project_id: str,
    story_id: str,
    body: PushRequest = PushRequest(),
    db: AsyncSession = Depends(get_db),
):
    project, story, feature = await _get_story_context(project_id, story_id, db)

    # Push gate (Day 5-gated)
    cq_snap = _load_json(story.code_quality_snapshot or "")
    blocked = _push_gate_check(story, cq_snap if cq_snap else None)
    if blocked:
        raise HTTPException(status_code=400, detail=f"Push blocked: {blocked}")

    workspace = project.workspace_path
    if not workspace:
        raise HTTPException(status_code=400, detail="No workspace configured")

    # Resolve credentials - prefer existing project config; accept override from request
    repo_url = project.github_repo_url or body.repo_url
    if not repo_url:
        raise HTTPException(
            status_code=400,
            detail="No repository URL configured. Provide repo_url in the request body.",
        )

    pat: str | None = None
    if project.github_pat_encrypted:
        try:
            pat = decrypt_value(project.github_pat_encrypted)
        except Exception:
            pat = None

    if not pat and body.pat:
        pat = body.pat
        # Persist new credentials securely - never log the PAT
        project.github_repo_url = repo_url
        project.github_pat_encrypted = encrypt_value(body.pat)
        await db.commit()
        logger.info("Saved new repository credentials for project %s", project_id)

    if not pat:
        raise HTTPException(
            status_code=400,
            detail="No access token available. Provide pat in the request body.",
        )

    # Validate credentials before pushing
    from app.services.github_service import GitHubService
    github = GitHubService(pat)
    try:
        repo_info = await github.validate_repo(repo_url)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Repository validation failed: {str(exc)[:200]}")

    # Determine branch - use existing current branch from orchestrator convention or default
    branch = f"codegen/story/{story.title[:30].lower().replace(' ', '-')}"

    try:
        github.create_branch(workspace, branch)
    except Exception as exc:
        logger.warning("Branch creation: %s", exc)

    commit_msg = body.commit_message or f"feat: {story.title} - Aegis delivery"
    try:
        github.commit_and_push(workspace, commit_msg, branch)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Push failed: {str(exc)[:300]}")

    # Create PR if not already done
    pr_url = None
    try:
        base = repo_info.get("default_branch", "main")
        pr_data = await github.create_pull_request(
            repo_url, branch, base,
            f"feat: {story.title}",
            f"## Aegis Delivery\n\nStory: {story.title}\n\nQuality Gate: {story.test_status}",
        )
        pr_url = pr_data.get("url")
    except Exception as exc:
        logger.warning("PR creation skipped: %s", exc)

    return {
        "status": "pushed",
        "branch": branch,
        "repo": repo_url,
        "pr_url": pr_url,
        "commit_message": commit_msg,
    }


# ── Utility ───────────────────────────────────────────────────────────────────

def _ac_color_hex(index: int) -> str:
    palette = [
        "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
        "#06b6d4", "#f97316", "#84cc16", "#ec4899", "#6366f1",
    ]
    return palette[index % len(palette)]
