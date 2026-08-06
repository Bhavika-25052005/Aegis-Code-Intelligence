from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.crypto import encrypt_value

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=data.name,
        github_repo_url=data.github_repo_url,
        github_pat_encrypted=encrypt_value(data.github_pat) if data.github_pat else "",
        azure_devops_org_url=data.azure_devops_org_url,
        azure_devops_project=data.azure_devops_project,
        azure_devops_pat_encrypted=encrypt_value(data.azure_devops_pat) if data.azure_devops_pat else "",
        workspace_path=data.workspace_path,
        pr_strategy=data.pr_strategy,
        claude_max_budget_usd=data.claude_max_budget_usd,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = data.model_dump(exclude_unset=True)
    if "github_pat" in update_data:
        pat = update_data.pop("github_pat")
        project.github_pat_encrypted = encrypt_value(pat) if pat else ""
    if "azure_devops_pat" in update_data:
        pat = update_data.pop("azure_devops_pat")
        project.azure_devops_pat_encrypted = encrypt_value(pat) if pat else ""

    for key, value in update_data.items():
        setattr(project, key, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return {"status": "deleted"}
