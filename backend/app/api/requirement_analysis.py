import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.backlog import Feature, UserStory
from app.models.project import Project
from app.services.requirement_analyzer import (
    RequirementAnalyzer,
    RequirementAnalysisError,
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
    from app.services.requirement_analyzer import RequirementAnalyzer

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
