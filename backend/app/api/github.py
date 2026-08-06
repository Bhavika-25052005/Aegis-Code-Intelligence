from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.services.crypto import decrypt_value
from app.services.github_service import GitHubService

router = APIRouter(prefix="/projects/{project_id}/github", tags=["github"])


class ValidateResponse(BaseModel):
    valid: bool
    message: str
    repo_name: str = ""


class CloneResponse(BaseModel):
    status: str
    path: str


@router.post("/validate", response_model=ValidateResponse)
async def validate_github(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_repo_url or not project.github_pat_encrypted:
        raise HTTPException(status_code=400, detail="GitHub repo URL and PAT are required")

    pat = decrypt_value(project.github_pat_encrypted)
    github = GitHubService(pat)

    try:
        repo_info = await github.validate_repo(project.github_repo_url)
        return ValidateResponse(valid=True, message="Access verified", repo_name=repo_info["name"])
    except Exception as e:
        return ValidateResponse(valid=False, message=str(e))


@router.post("/clone", response_model=CloneResponse)
async def clone_repo(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_repo_url or not project.github_pat_encrypted:
        raise HTTPException(status_code=400, detail="GitHub repo URL and PAT are required")

    pat = decrypt_value(project.github_pat_encrypted)
    github = GitHubService(pat)

    from app.config import settings
    workspace = project.workspace_path or str(settings.get_workspace_path())

    try:
        clone_path = await github.clone_repo(project.github_repo_url, workspace)
        project.workspace_path = clone_path
        project.is_repo_cloned = True
        await db.commit()
        return CloneResponse(status="cloned", path=clone_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clone failed: {str(e)}")


@router.get("/branches")
async def list_branches(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.is_repo_cloned:
        raise HTTPException(status_code=400, detail="Repository not cloned yet")

    pat = decrypt_value(project.github_pat_encrypted)
    github = GitHubService(pat)
    branches = await github.list_branches(project.github_repo_url)
    return {"branches": branches}
