import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    github_repo_url: Mapped[str] = mapped_column(String(500), default="")
    github_pat_encrypted: Mapped[str] = mapped_column(String(500), default="")
    azure_devops_org_url: Mapped[str] = mapped_column(String(500), default="")
    azure_devops_project: Mapped[str] = mapped_column(String(255), default="")
    azure_devops_pat_encrypted: Mapped[str] = mapped_column(String(500), default="")
    workspace_path: Mapped[str] = mapped_column(String(500), default="")
    pr_strategy: Mapped[str] = mapped_column(String(50), default="per_story")
    is_repo_cloned: Mapped[bool] = mapped_column(Boolean, default=False)
    claude_max_budget_usd: Mapped[float] = mapped_column(Float, default=5.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    features = relationship("Feature", back_populates="project", cascade="all, delete-orphan")
    execution_runs = relationship("ExecutionRun", back_populates="project", cascade="all, delete-orphan")
    pull_requests = relationship("PullRequest", back_populates="project", cascade="all, delete-orphan")
