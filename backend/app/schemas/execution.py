from datetime import datetime
from pydantic import BaseModel


class ExecutionStartRequest(BaseModel):
    pr_strategy: str | None = None


class ExecutionStatusResponse(BaseModel):
    id: str
    project_id: str
    status: str
    current_task_id: str | None
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    started_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True
