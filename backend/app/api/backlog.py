from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.project import Project
from app.models.backlog import Feature, UserStory, Task
from app.schemas.backlog import BacklogTreeResponse, FeatureResponse, AzureDevOpsImportRequest
from app.services.backlog_parser import BacklogParser
from app.services.azure_devops import AzureDevOpsClient

router = APIRouter(prefix="/projects/{project_id}/backlog", tags=["backlog"])


@router.post("/upload")
async def upload_backlog(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    filename = file.filename or "upload.csv"

    parser = BacklogParser()
    try:
        parsed = parser.parse(content, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await _save_parsed_backlog(db, project_id, parsed)
    return {"status": "imported", "features": len(parsed)}


@router.post("/azure-devops")
async def import_from_azure_devops(
    project_id: str,
    request: AzureDevOpsImportRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    client = AzureDevOpsClient(request.org_url, request.project, request.pat)
    try:
        parsed = await client.get_backlog_items(request.query)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Azure DevOps error: {str(e)}")

    await _save_parsed_backlog(db, project_id, parsed)
    return {"status": "imported", "features": len(parsed)}


@router.get("", response_model=BacklogTreeResponse)
async def get_backlog(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id)
        .options(selectinload(Feature.user_stories).selectinload(UserStory.tasks))
        .order_by(Feature.order)
    )
    features = result.scalars().all()

    total_tasks = 0
    completed_tasks = 0
    pending_tasks = 0
    for f in features:
        for s in f.user_stories:
            for t in s.tasks:
                total_tasks += 1
                if t.status == "completed":
                    completed_tasks += 1
                elif t.status == "pending":
                    pending_tasks += 1

    return BacklogTreeResponse(
        project_id=project_id,
        features=[FeatureResponse.model_validate(f) for f in features],
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
    )


@router.delete("/features/{feature_id}")
async def delete_feature(project_id: str, feature_id: str, db: AsyncSession = Depends(get_db)):
    feature = await db.get(Feature, feature_id)
    if not feature or feature.project_id != project_id:
        raise HTTPException(status_code=404, detail="Feature not found")
    await db.delete(feature)
    await db.commit()
    return {"status": "deleted"}


async def _save_parsed_backlog(db: AsyncSession, project_id: str, parsed: list[dict]):
    for f_idx, feature_data in enumerate(parsed):
        feature = Feature(
            project_id=project_id,
            external_id=feature_data.get("external_id", ""),
            title=feature_data["title"],
            description=feature_data.get("description", ""),
            order=f_idx,
        )
        db.add(feature)
        await db.flush()

        for s_idx, story_data in enumerate(feature_data.get("user_stories", [])):
            story = UserStory(
                feature_id=feature.id,
                external_id=story_data.get("external_id", ""),
                title=story_data["title"],
                description=story_data.get("description", ""),
                acceptance_criteria=story_data.get("acceptance_criteria", ""),
                order=s_idx,
            )
            db.add(story)
            await db.flush()

            for t_idx, task_data in enumerate(story_data.get("tasks", [])):
                task = Task(
                    user_story_id=story.id,
                    external_id=task_data.get("external_id", ""),
                    title=task_data["title"],
                    description=task_data.get("description", ""),
                    order=t_idx,
                )
                db.add(task)

    await db.commit()
