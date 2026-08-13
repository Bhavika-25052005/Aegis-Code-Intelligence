import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="features")
    user_stories = relationship("UserStory", back_populates="feature", cascade="all, delete-orphan", order_by="UserStory.order")


class UserStory(Base):
    __tablename__ = "user_stories"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    feature_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("features.id", ondelete="CASCADE"),
    )
    external_id: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")

    # Requirement Intelligence
    requirement_analysis: Mapped[str] = mapped_column(Text, default="")
    requirement_analysis_status: Mapped[str] = mapped_column(
        String(20),
        default="not_analyzed",
    )
    requirement_analysis_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Day 2 - Implementation Intelligence
    implementation_plan: Mapped[str] = mapped_column(
        Text,
        default="",
    )
    implementation_plan_status: Mapped[str] = mapped_column(
        String(20),
        default="not_planned",
    )
    implementation_plan_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Day 3 - Test Intelligence
    test_plan: Mapped[str] = mapped_column(Text, default="")
    test_status: Mapped[str] = mapped_column(String(30), default="not_started")
    test_summary: Mapped[str] = mapped_column(Text, default="")
    test_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Day 4 - Quality Snapshot (cached computed quality data)
    quality_snapshot: Mapped[str] = mapped_column(Text, default="")
    quality_snapshot_hash: Mapped[str] = mapped_column(String(64), default="")

    order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    feature = relationship("Feature", back_populates="user_stories")
    tasks = relationship(
        "Task",
        back_populates="user_story",
        cascade="all, delete-orphan",
        order_by="Task.order",
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_story_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_stories.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    claude_session_id: Mapped[str] = mapped_column(String(100), default="")
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user_story = relationship("UserStory", back_populates="tasks")
