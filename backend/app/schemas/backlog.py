from datetime import datetime
from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    external_id: str
    title: str
    description: str
    order: int
    status: str
    retry_count: int
    error_message: str
    completed_at: datetime | None

    class Config:
        from_attributes = True


class UserStoryResponse(BaseModel):
    id: str
    external_id: str
    title: str
    description: str
    acceptance_criteria: str
    order: int
    status: str
    tasks: list[TaskResponse] = []

    class Config:
        from_attributes = True


class FeatureResponse(BaseModel):
    id: str
    external_id: str
    title: str
    description: str
    order: int
    status: str
    user_stories: list[UserStoryResponse] = []

    class Config:
        from_attributes = True


class BacklogTreeResponse(BaseModel):
    project_id: str
    features: list[FeatureResponse] = []
    total_tasks: int = 0
    completed_tasks: int = 0
    pending_tasks: int = 0


class AzureDevOpsImportRequest(BaseModel):
    org_url: str
    project: str
    pat: str
    query: str = ""
