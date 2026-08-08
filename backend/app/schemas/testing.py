from datetime import datetime
from pydantic import BaseModel


class TestRunResponse(BaseModel):
    id: str
    task_id: str
    test_type: str
    status: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    coverage_percentage: float
    duration_seconds: float
    error_summary: str
    fix_attempt: int
    created_at: datetime

    class Config:
        from_attributes = True


class TestReportResponse(BaseModel):
    id: str
    project_id: str
    scope_type: str
    scope_id: str
    overall_status: str
    unit_coverage: float
    integration_passed: bool
    performance_passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    report_summary: str
    created_at: datetime

    class Config:
        from_attributes = True


class TestResultSummary(BaseModel):
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    coverage_percentage: float = 0.0
    duration_seconds: float = 0.0
    error_summary: str = ""
    test_output: str = ""


class ManualTestRequest(BaseModel):
    scope: str  # "regression" or "pr"
    branch: str | None = None
    test_types: list[str] = ["unit", "integration"]


class ManualTestResponse(BaseModel):
    test_run_id: str
    status: str


class CustomTestRequest(BaseModel):
    objective: str


class CustomTestResponse(BaseModel):
    test_id: str
    detected_type: str
    file: str
    status: str
    repair_attempts: int
    output: str
