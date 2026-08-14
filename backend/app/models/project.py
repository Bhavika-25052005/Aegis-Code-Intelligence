import uuid
from datetime import datetime

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Float,
    Integer,
    Text,
    ForeignKey,
    UniqueConstraint,
)
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

    # Implementation Intelligence - Repository Intelligence index state
    repository_index_commit: Mapped[str] = mapped_column(
        String(64),
        default="",
    )
    repository_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    features = relationship("Feature", back_populates="project", cascade="all, delete-orphan")
    execution_runs = relationship("ExecutionRun", back_populates="project", cascade="all, delete-orphan")
    pull_requests = relationship("PullRequest", back_populates="project", cascade="all, delete-orphan")
    repository_files = relationship(
        "RepositoryFile",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class RepositoryFile(Base):
    __tablename__ = "repository_files"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "relative_path",
            name="uq_repository_file_project_path",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    relative_path: Mapped[str] = mapped_column(String(1000))
    extension: Mapped[str] = mapped_column(String(30), default="")
    category: Mapped[str] = mapped_column(String(50), default="source")

    # Newline-delimited metadata. No complete source code is stored.
    symbols_json: Mapped[str] = mapped_column(Text, default="")
    imports_json: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    project = relationship(
        "Project",
        back_populates="repository_files",
    )


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("project_id", "story_id", "node_key", name="uq_graph_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    story_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    node_key: Mapped[str] = mapped_column(String(500))
    node_type: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    graph_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    story_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_key: Mapped[str] = mapped_column(String(500))
    target_key: Mapped[str] = mapped_column(String(500))
    relation_type: Mapped[str] = mapped_column(String(50))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    graph_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
