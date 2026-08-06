from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    github_repo_url: str = ""
    github_pat: str = ""
    azure_devops_org_url: str = ""
    azure_devops_project: str = ""
    azure_devops_pat: str = ""
    workspace_path: str = ""
    pr_strategy: str = "per_story"
    claude_max_budget_usd: float = 5.0


class ProjectUpdate(BaseModel):
    name: str | None = None
    github_repo_url: str | None = None
    github_pat: str | None = None
    azure_devops_org_url: str | None = None
    azure_devops_project: str | None = None
    azure_devops_pat: str | None = None
    workspace_path: str | None = None
    pr_strategy: str | None = None
    claude_max_budget_usd: float | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    github_repo_url: str
    azure_devops_org_url: str
    azure_devops_project: str
    workspace_path: str
    pr_strategy: str
    is_repo_cloned: bool
    claude_max_budget_usd: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
