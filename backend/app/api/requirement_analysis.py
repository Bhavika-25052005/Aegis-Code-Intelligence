import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.backlog import Feature, UserStory
from app.models.project import Project
from app.services.crypto import decrypt_value
from app.services.github_service import GitHubService
from app.services.data_model_generator import DataModelGenerator, DataModelGenerationError
from app.services.data_model_serializer import DataModelSerializer
from app.services.knowledge_graph import KnowledgeGraphService
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


class DataModelGenerateRequest(BaseModel):
    user_prompt: Optional[str] = None


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


# ── Requirement Intelligence endpoints ───────────────────────────────────────

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


# ── Implementation Intelligence endpoints ────────────────────────────────────

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
        "data_model": _load_json_object(story.data_model),
        "data_model_status": story.data_model_status,
        "data_model_approved_at": story.data_model_approved_at,
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

    # Auto-generate data model alongside the plan (non-blocking)
    try:
        from app.services.data_model_generator import DataModelGenerator, DataModelGenerationError
        existing_dm = _load_json_object(story.data_model)
        dm_gen = DataModelGenerator(
            workspace_path=workspace,
            max_budget_usd=min(project.claude_max_budget_usd, 1.5),
        )
        data_model = await dm_gen.generate(
            feature=feature, story=story,
            requirement_analysis=requirement, implementation_plan=plan,
            existing_data_model=existing_dm,
            repository_context={"files": []},
        )
        story.data_model = json.dumps(data_model)
        story.data_model_status = "draft"
        story.data_model_approved_at = None
        await db.commit()
        await db.refresh(story)
    except Exception as _dm_exc:
        logger.warning("Data model auto-generation skipped: %s", _dm_exc)

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
        "data_model": _load_json_object(story.data_model),
        "data_model_status": story.data_model_status,
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


# ── Knowledge Graph ───────────────────────────────────────────────────────────

from app.services.knowledge_graph import KnowledgeGraphService
_kg_svc = KnowledgeGraphService()


@router.get("/{story_id}/knowledge-graph")
async def get_knowledge_graph(
    project_id: str,
    story_id: str,
    focus_node: Optional[str] = Query(default=None),
    depth: int = Query(default=1, ge=1, le=3),
    node_types: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    _, _, story = await get_story_context(project_id, story_id, db)
    status = getattr(story, "graph_status", "not_generated") or "not_generated"

    if status == "not_generated":
        return {
            "status": "not_generated",
            "nodes": [],
            "edges": [],
            "stats": {"nodes": 0, "edges": 0},
            "version": 0,
            "generated_at": None,
        }

    types_filter = [t.strip() for t in node_types.split(",")] if node_types else None
    graph = await _kg_svc.get_graph(
        project_id=project_id,
        story_id=story_id,
        focus_node=focus_node,
        depth=depth,
        node_types=types_filter,
        search=search,
        db=db,
    )
    return {
        "status": status,
        "version": getattr(story, "graph_version", 0) or 0,
        "generated_at": story.graph_generated_at.isoformat() if getattr(story, "graph_generated_at", None) else None,
        **graph,
    }


@router.post("/{story_id}/knowledge-graph/generate")
async def generate_knowledge_graph(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    project, _, story = await get_story_context(project_id, story_id, db)
    if not _load_json_object(story.implementation_plan):
        raise HTTPException(status_code=400, detail="Generate an implementation plan first.")
    result = await _kg_svc.generate_initial_graph(project, story, db)
    return {"status": "ok", **result}


@router.post("/{story_id}/knowledge-graph/impact")
async def analyze_impact(
    project_id: str,
    story_id: str,
    node_key: str = Query(...),
    depth: int = Query(default=2, ge=1, le=3),
    db: AsyncSession = Depends(get_db),
):
    _, _, story = await get_story_context(project_id, story_id, db)
    if (getattr(story, "graph_status", "not_generated") or "not_generated") == "not_generated":
        raise HTTPException(status_code=400, detail="Generate the graph first.")
    return await _kg_svc.analyze_impact(
        project_id=project_id,
        story_id=story_id,
        node_key=node_key,
        depth=depth,
        db=db,
    )


@router.post("/{story_id}/knowledge-graph/enhance")
async def enhance_knowledge_graph(
    project_id: str,
    story_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Use Claude to add semantic relationships (USES, CALLS, IMPLEMENTS) to the graph."""
    project, _, story = await get_story_context(project_id, story_id, db)
    if (getattr(story, "graph_status", "not_generated") or "not_generated") == "not_generated":
        raise HTTPException(status_code=400, detail="Generate the base graph first.")

    workspace = project.workspace_path or ""
    result = await _kg_svc.enhance_with_claude(project, story, workspace, db)
    return {"status": "ok", **result}


# ── Data Model endpoints ──────────────────────────────────────────────────────

from app.services.data_model_generator import DataModelGenerator, DataModelGenerationError
from app.services.data_model_serializer import DataModelSerializer
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel as PydanticBaseModel


class DataModelGenerateRequest(PydanticBaseModel):
    user_prompt: Optional[str] = None


@router.post("/{story_id}/data-model")
async def generate_data_model(
    project_id: str,
    story_id: str,
    body: DataModelGenerateRequest = DataModelGenerateRequest(),
    db: AsyncSession = Depends(get_db),
):
    project, feature, story = await get_story_context(project_id, story_id, db)
    plan = _load_json_object(story.implementation_plan)
    if not plan:
        raise HTTPException(status_code=400, detail="Generate an implementation plan first.")

    req = _load_json_object(story.requirement_analysis) or {}
    existing = _load_json_object(story.data_model)
    workspace = project.workspace_path or ""

    from app.models.project import RepositoryFile
    rf_result = await db.execute(select(RepositoryFile).where(RepositoryFile.project_id == project_id))
    repo_files = rf_result.scalars().all()
    repo_context = {"files": [{"path": rf.relative_path, "category": rf.category} for rf in repo_files[:40]]}

    generator = DataModelGenerator(workspace_path=workspace, max_budget_usd=min(project.claude_max_budget_usd, 1.5))
    try:
        data_model = await generator.generate(
            feature=feature, story=story,
            requirement_analysis=req, implementation_plan=plan,
            existing_data_model=existing, repository_context=repo_context,
            user_prompt=body.user_prompt,
        )
    except DataModelGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    story.data_model = json.dumps(data_model)
    story.data_model_status = "draft"
    story.data_model_approved_at = None
    await db.commit()
    return {"data_model": data_model, "data_model_status": "draft"}


@router.patch("/{story_id}/data-model")
async def update_data_model(
    project_id: str, story_id: str, body: dict, db: AsyncSession = Depends(get_db),
):
    """Save an edited data model directly."""
    _, _, story = await get_story_context(project_id, story_id, db)
    validated = DataModelGenerator._validate(body)
    story.data_model = json.dumps(validated)
    if story.data_model_status == "approved":
        story.data_model_status = "draft"
        story.data_model_approved_at = None
    await db.commit()
    return {"data_model": validated, "data_model_status": story.data_model_status}


@router.post("/{story_id}/data-model/upload")
async def upload_data_model(
    project_id: str, story_id: str,
    file: "UploadFile" = None,
    db: AsyncSession = Depends(get_db),
):
    """Upload a data model from a JSON/SQL/DBML file."""
    from fastapi import UploadFile as FUploadFile, File as FFile
    _, _, story = await get_story_context(project_id, story_id, db)
    if file is None:
        raise HTTPException(status_code=400, detail="No file provided.")
    content = await file.read()
    if len(content) > 1_048_576:
        raise HTTPException(status_code=400, detail="File too large (max 1MB).")
    filename = file.filename or "upload.json"
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "json":
        try:
            raw = json.loads(content.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
        data_model = DataModelGenerator._validate(raw)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '.{ext}'. Upload a .json file.")

    story.data_model = json.dumps(data_model)
    story.data_model_status = "draft"
    story.data_model_approved_at = None
    await db.commit()
    return {"data_model": data_model, "data_model_status": "draft"}


@router.post("/{story_id}/data-model/approve")
async def approve_data_model(project_id: str, story_id: str, db: AsyncSession = Depends(get_db)):
    _, _, story = await get_story_context(project_id, story_id, db)
    if not story.data_model:
        raise HTTPException(status_code=400, detail="No data model to approve.")
    story.data_model_status = "approved"
    story.data_model_approved_at = datetime.utcnow()
    await db.commit()
    return {"status": "approved", "data_model_status": "approved"}


@router.post("/{story_id}/data-model/reopen")
async def reopen_data_model(project_id: str, story_id: str, db: AsyncSession = Depends(get_db)):
    _, _, story = await get_story_context(project_id, story_id, db)
    story.data_model_status = "draft"
    story.data_model_approved_at = None
    await db.commit()
    return {"status": "draft"}


@router.get("/{story_id}/data-model/download")
async def download_data_model(
    project_id: str, story_id: str,
    format: str = Query(default="json"),
    db: AsyncSession = Depends(get_db),
):
    _, _, story = await get_story_context(project_id, story_id, db)
    if not story.data_model:
        raise HTTPException(status_code=404, detail="No data model exists.")
    model = json.loads(story.data_model)
    content = DataModelSerializer().serialize(model, format)
    media = {"json": "application/json", "sql": "text/plain", "dbml": "text/plain"}.get(format, "text/plain")
    return FastAPIResponse(
        content=content, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="data_model.{format}"'},
    )
