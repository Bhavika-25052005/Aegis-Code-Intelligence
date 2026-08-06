import uuid
from datetime import datetime

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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    feature_id: Mapped[str] = mapped_column(String(36), ForeignKey("features.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    feature = relationship("Feature", back_populates="user_stories")
    tasks = relationship("Task", back_populates="user_story", cascade="all, delete-orphan", order_by="Task.order")


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
