import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.backlog import Feature, UserStory
from app.models.project import Project
from app.services.crypto import decrypt_value
from app.services.github_service import GitHubService
from app.services.requirement_analyzer import (
    RequirementAnalyzer,
    RequirementAnalysisError,
)
from app.services.repository_intelligence import RepositoryIntelligence
from app.services.implementation_planner import (
    ImplementationPlanner,
    ImplementationPlanningError,
)

router = APIRouter(
    prefix="/projects/{project_id}/requirements",
    tags=["Requirement Intelligence"],
)


async def get_story_context(
    project_id: str,
    story_id: str,
    db: AsyncSession,
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    result = await db.execute(
        select(UserStory, Feature)
        .join(Feature, UserStory.feature_id == Feature.id)
        .where(
            UserStory.id == story_id,
            Feature.project_id == project_id,
        )
        .options(selectinload(UserStory.tasks))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="User story not found.")

    story, feature = row
    return project, feature, story


def story_analysis_response(
    project: Project,
    feature: Feature,
    story: UserStory,
):
    analysis = None
    if story.requirement_analysis:
        try:
            analysis = json.loads(story.requirement_analysis)
        except json.JSONDecodeError:
            analysis = None

    return {
        "project_id": project.id,
        "feature_id": feature.id,
        "feature_title": feature.title,
        "user_story_id": story.id,
        "user_story_title": story.title,
        "user_story_description": story.description,
        "original_acceptance_criteria": story.acceptance_criteria,
        "analysis": analysis,
        "status": story.requirement_analysis_status,
        "approved_at": story.requirement_analysis_approved_at,
    }


def _load_json_object(value: str) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def _resolve_workspace(
    project: Project,
    db: AsyncSession,
) -> str:
    # GitHub: clone only when missing, then reuse project.workspace_path.
    if project.github_repo_url and project.github_pat_encrypted:
        if (
            project.is_repo_cloned
            and project.workspace_path
            and Path(project.workspace_path).exists()
        ):
            return project.workspace_path

        pat = decrypt_value(project.github_pat_encrypted)
        github = GitHubService(pat)
        base_workspace = (
            project.workspace_path
            if project.workspace_path
            else str(settings.get_workspace_path())
        )
        clone_path = await github.clone_repo(
            project.github_repo_url,
            base_workspace,
        )
        project.workspace_path = clone_path
        project.is_repo_cloned = True
        await db.commit()
        await db.refresh(project)
        return clone_path

    # No GitHub: use local workspace directly.
    if not project.workspace_path:
        raise HTTPException(
            status_code=400,
            detail="Configure a GitHub repository or a local workspace path.",
        )
    workspace = Path(project.workspace_path)
    if not workspace.exists() or not workspace.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Workspace does not exist: {workspace}",
        )
    return str(workspace)


# ── Day 1 endpoints ──────────────────────────────────────────────────────────

@router.get("/{story_id}")
async def get_analysis(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )
    return story_analysis_response(project, feature, story)


@router.post("/{story_id}/analyze")
async def analyze_requirement(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )

    if project.workspace_path:
        workspace = Path(project.workspace_path)
    else:
        workspace = settings.get_workspace_path()

    analyzer = RequirementAnalyzer(
        workspace_path=str(workspace),
        max_budget_usd=min(project.claude_max_budget_usd, 1.0),
    )

    try:
        analysis = await analyzer.analyze(feature, story)
    except RequirementAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    story.requirement_analysis = json.dumps(analysis)
    story.requirement_analysis_status = "draft"
    story.requirement_analysis_approved_at = None
    # Requirement changed — invalidate old implementation plan
    story.implementation_plan = ""
    story.implementation_plan_status = "not_planned"
    story.implementation_plan_approved_at = None
    await db.commit()
    await db.refresh(story)

    return story_analysis_response(project, feature, story)


@router.patch("/{story_id}")
async def update_analysis(
    project_id: str,
    story_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )

    if not story.requirement_analysis:
        raise HTTPException(
            status_code=400,
            detail="No analysis exists to update.",
        )

    try:
        current = json.loads(story.requirement_analysis)
    except json.JSONDecodeError:
        current = {}

    allowed_fields = {
        "summary",
        "acceptance_criteria",
        "functional_rules",
        "edge_cases",
        "assumptions",
        "dependencies",
        "ambiguities",
        "risks",
        "questions",
        "risk_level",
    }
    list_fields = allowed_fields - {"summary", "risk_level"}

    for field, value in body.items():
        if field not in allowed_fields:
            continue
        if field == "summary":
            current[field] = str(value)
        elif field == "risk_level":
            v = str(value).lower()
            current[field] = v if v in {"low", "medium", "high", "critical"} else "medium"
        elif field in list_fields:
            if not isinstance(value, list):
                raise HTTPException(status_code=422, detail=f"'{field}' must be a list.")
            current[field] = [str(i) for i in value if str(i).strip()]

    story.requirement_analysis = json.dumps(current)
    # Any manual edit resets approval — human must re-approve.
    story.requirement_analysis_status = "draft"
    story.requirement_analysis_approved_at = None
    # Requirement changed — invalidate old implementation plan
    story.implementation_plan = ""
    story.implementation_plan_status = "not_planned"
    story.implementation_plan_approved_at = None
    await db.commit()
    await db.refresh(story)

    return story_analysis_response(project, feature, story)


@router.post("/{story_id}/approve")
async def approve_analysis(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )

    if not story.requirement_analysis:
        raise HTTPException(
            status_code=400,
            detail="Analyze the requirement before approving it.",
        )

    story.requirement_analysis_status = "approved"
    story.requirement_analysis_approved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(story)

    return story_analysis_response(project, feature, story)


@router.post("/{story_id}/reopen")
async def reopen_analysis(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )

    story.requirement_analysis_status = "draft"
    story.requirement_analysis_approved_at = None
    await db.commit()
    await db.refresh(story)

    return story_analysis_response(project, feature, story)


# ── Day 2 endpoints ──────────────────────────────────────────────────────────

@router.get("/{story_id}/implementation-plan")
async def get_implementation_plan(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )
    return {
        "project_id": project.id,
        "feature_id": feature.id,
        "feature_title": feature.title,
        "user_story_id": story.id,
        "user_story_title": story.title,
        "requirement_status": story.requirement_analysis_status,
        "implementation_plan": _load_json_object(story.implementation_plan),
        "implementation_plan_status": story.implementation_plan_status,
        "approved_at": story.implementation_plan_approved_at,
    }


@router.post("/{story_id}/implementation-plan")
async def generate_implementation_plan(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(
        project_id, story_id, db
    )

    if story.requirement_analysis_status != "approved":
        raise HTTPException(
            status_code=400,
            detail=(
                "Approve Requirement Intelligence before "
                "implementation planning."
            ),
        )

    requirement = _load_json_object(story.requirement_analysis)
    if not requirement:
        raise HTTPException(
            status_code=400,
            detail="Approved requirement could not be loaded.",
        )

    workspace = await _resolve_workspace(project, db)

    repository = RepositoryIntelligence(
        project=project,
        db=db,
        workspace_path=workspace,
    )
    repository_context = await repository.find_relevant(
        feature,
        story,
        requirement,
    )

    planner = ImplementationPlanner(
        workspace_path=workspace,
        max_budget_usd=min(project.claude_max_budget_usd, 1.5),
    )

    try:
        plan = await planner.create_plan(
            feature,
            story,
            requirement,
            repository_context,
        )
    except ImplementationPlanningError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    story.implementation_plan = json.dumps(plan)
    story.implementation_plan_status = "draft"
    story.implementation_plan_approved_at = None
    await db.commit()
    await db.refresh(story)

    return {
        "project_id": project.id,
        "feature_id": feature.id,
        "feature_title": feature.title,
        "user_story_id": story.id,
        "user_story_title": story.title,
        "requirement_status": story.requirement_analysis_status,
        "implementation_plan": plan,
        "implementation_plan_status": story.implementation_plan_status,
        "approved_at": story.implementation_plan_approved_at,
    }


@router.patch("/{story_id}/implementation-plan")
async def update_implementation_plan(
    project_id: str,
    story_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    _, _, story = await get_story_context(project_id, story_id, db)

    if not story.implementation_plan:
        raise HTTPException(status_code=400, detail="No implementation plan to update.")

    try:
        current = json.loads(story.implementation_plan)
    except json.JSONDecodeError:
        current = {}

    # Allow editing: work_summary, architecture_notes, planned_changes, task_plan approaches/related_files, risks, out_of_scope
    if "work_summary" in body:
        current["work_summary"] = str(body["work_summary"])

    for list_field in ("architecture_notes", "risks", "out_of_scope", "dependencies"):
        if list_field in body:
            v = body[list_field]
            if not isinstance(v, list):
                raise HTTPException(status_code=422, detail=f"'{list_field}' must be a list.")
            current[list_field] = [str(i) for i in v if str(i).strip()]

    # Allow editing planned_changes (path/action/purpose/reason per entry)
    if "planned_changes" in body:
        changes = body["planned_changes"]
        if not isinstance(changes, list):
            raise HTTPException(status_code=422, detail="'planned_changes' must be a list.")
        current["planned_changes"] = [
            {
                "path": str(c.get("path", "")),
                "action": str(c.get("action", "create")),
                "purpose": str(c.get("purpose", "")),
                "reason": str(c.get("reason", "")),
                "acceptance_criteria": c.get("acceptance_criteria", []),
            }
            for c in changes if c.get("path")
        ]

    # Allow editing task approaches and related_files
    if "task_plan" in body:
        task_map = {t["task_id"]: t for t in current.get("task_plan", [])}
        for update in body["task_plan"]:
            tid = update.get("task_id")
            if tid and tid in task_map:
                if "approach" in update:
                    task_map[tid]["approach"] = str(update["approach"])
                if "related_files" in update:
                    task_map[tid]["related_files"] = [str(f) for f in update["related_files"]]
        current["task_plan"] = list(task_map.values())

    story.implementation_plan = json.dumps(current)
    # Any edit resets approval
    story.implementation_plan_status = "draft"
    story.implementation_plan_approved_at = None
    await db.commit()
    await db.refresh(story)

    return {
        "project_id": project_id,
        "user_story_id": story.id,
        "implementation_plan": current,
        "implementation_plan_status": story.implementation_plan_status,
        "approved_at": story.implementation_plan_approved_at,
    }


@router.post("/{story_id}/implementation-plan/approve")
async def approve_implementation_plan(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    _, _, story = await get_story_context(project_id, story_id, db)

    if story.requirement_analysis_status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Requirement Intelligence is not approved.",
        )
    if not story.implementation_plan:
        raise HTTPException(
            status_code=400,
            detail="Generate the implementation plan first.",
        )

    story.implementation_plan_status = "approved"
    story.implementation_plan_approved_at = datetime.utcnow()
    await db.commit()

    return {
        "status": "approved",
        "approved_at": story.implementation_plan_approved_at,
    }


@router.post("/{story_id}/implementation-plan/reopen")
async def reopen_implementation_plan(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    _, _, story = await get_story_context(project_id, story_id, db)
    story.implementation_plan_status = "draft"
    story.implementation_plan_approved_at = None
    await db.commit()
    return {"status": "draft"}
