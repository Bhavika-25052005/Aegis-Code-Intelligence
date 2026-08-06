import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(100), default="")
    execution_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("execution_runs.id"), nullable=True)
    test_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="running")
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    skipped_tests: Mapped[int] = mapped_column(Integer, default=0)
    coverage_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    report_json: Mapped[str] = mapped_column(Text, default="")
    error_summary: Mapped[str] = mapped_column(Text, default="")
    fix_attempt: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TestReport(Base):
    __tablename__ = "test_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("execution_runs.id"), nullable=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"))
    scope_type: Mapped[str] = mapped_column(String(50), default="task")
    scope_id: Mapped[str] = mapped_column(String(36), default="")
    overall_status: Mapped[str] = mapped_column(String(50), default="pending")
    unit_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    integration_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    performance_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    report_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
