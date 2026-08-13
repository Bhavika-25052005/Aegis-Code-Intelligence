"""
Quality Traceability + Delivery API.

Endpoints:
  GET  /projects/{project_id}/quality/{story_id}                 — full quality data
  GET  /projects/{project_id}/quality/{story_id}/run-history     — execution run history
  GET  /projects/{project_id}/quality/{story_id}/report.pdf      — filtered PDF
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/quality", tags=["quality"])
reporter = QualityReporter()


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


def _push_gate_check(story) -> str | None:
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

    # Build/restore traceability snapshot (cached — only recomputes when test_plan changes)
    traceability_data = await reporter.ensure_traceability(
        story, requirement, project.workspace_path or "", test_runs=test_runs
    )
    # Persist snapshot and any mapping changes
    await db.commit()

    traceability = {"tests": traceability_data["tests"]}
    # Use summary from snapshot (already computed with TestRun records)
    summary = traceability_data["summary"]

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

    # Push gate
    push_blocked_reason = _push_gate_check(story)

    # README status — check if workspace has README.md
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

    # Write to a temp file — FastAPI FileResponse handles cleanup
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

    # Push gate
    blocked = _push_gate_check(story)
    if blocked:
        raise HTTPException(status_code=400, detail=f"Push blocked: {blocked}")

    workspace = project.workspace_path
    if not workspace:
        raise HTTPException(status_code=400, detail="No workspace configured")

    # Resolve credentials — prefer existing project config; accept override from request
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
        # Persist new credentials securely — never log the PAT
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

    # Determine branch — use existing current branch from orchestrator convention or default
    branch = f"codegen/story/{story.title[:30].lower().replace(' ', '-')}"

    try:
        github.create_branch(workspace, branch)
    except Exception as exc:
        logger.warning("Branch creation: %s", exc)

    commit_msg = body.commit_message or f"feat: {story.title} — Aegis delivery"
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
