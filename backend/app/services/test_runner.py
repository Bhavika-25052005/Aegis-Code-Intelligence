import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.testing import TestRun, TestReport
from app.models.backlog import Task, UserStory, Feature
from app.services.claude_runner import ClaudeRunner
from app.services.prompt_builder import PromptBuilder
from app.services.websocket_manager import manager as ws_manager
from app.config import settings

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 3


@dataclass
class TestResult:
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    coverage_percentage: float = 0.0
    duration_seconds: float = 0.0
    error_summary: str = ""
    raw_output: str = ""


class TestRunnerService:
    def __init__(self, project_id: str, db: AsyncSession, workspace: str, budget: float):
        self.project_id = project_id
        self.db = db
        self.workspace = workspace
        self.budget = budget
        self.prompt_builder = PromptBuilder()

    async def run_unit_tests(
        self,
        task: Task,
        execution_run_id: str | None,
        modified_files: list[str],
    ) -> TestResult:
        await self._broadcast("test_started", {"task_id": task.id, "test_type": "unit"})

        prompt = self.prompt_builder.build_test_prompt(task, modified_files, "unit")
        runner = ClaudeRunner(self.workspace, self.budget)

        start_time = datetime.utcnow()
        result = await runner.execute(prompt)
        duration = (datetime.utcnow() - start_time).total_seconds()

        test_result = self._parse_test_result(result.output if result.success else result.error, duration)

        # Save TestRun record
        test_run = TestRun(
            task_id=task.id,
            execution_run_id=execution_run_id,
            test_type="unit",
            status="passed" if test_result.passed else "failed",
            total_tests=test_result.total_tests,
            passed_tests=test_result.passed_tests,
            failed_tests=test_result.failed_tests,
            coverage_percentage=test_result.coverage_percentage,
            duration_seconds=test_result.duration_seconds,
            error_summary=test_result.error_summary[:2000],
            fix_attempt=0,
        )
        self.db.add(test_run)
        await self.db.commit()

        await self._broadcast("test_completed", {
            "task_id": task.id,
            "test_type": "unit",
            "passed": test_result.passed,
            "total": test_result.total_tests,
            "failed": test_result.failed_tests,
            "coverage": test_result.coverage_percentage,
        })

        return test_result

    async def fix_and_retest(
        self,
        task: Task,
        execution_run_id: str | None,
        test_result: TestResult,
        modified_files: list[str],
    ) -> TestResult:
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            await self._broadcast("fix_attempt", {
                "task_id": task.id,
                "attempt": attempt,
                "reason": test_result.error_summary[:200],
            })
            await self._broadcast("claude_output", {
                "message": f"Fix attempt {attempt}/{MAX_FIX_ATTEMPTS}: {task.title}",
            })

            fix_prompt = self.prompt_builder.build_fix_prompt(
                task, test_result.raw_output, modified_files, attempt
            )
            runner = ClaudeRunner(self.workspace, self.budget)
            fix_result = await runner.execute(fix_prompt)

            start_time = datetime.utcnow()
            duration = (datetime.utcnow() - start_time).total_seconds()

            new_test_result = self._parse_test_result(
                fix_result.output if fix_result.success else fix_result.error, duration
            )

            # Save fix attempt TestRun
            test_run = TestRun(
                task_id=task.id,
                execution_run_id=execution_run_id,
                test_type="unit",
                status="passed" if new_test_result.passed else "failed",
                total_tests=new_test_result.total_tests,
                passed_tests=new_test_result.passed_tests,
                failed_tests=new_test_result.failed_tests,
                coverage_percentage=new_test_result.coverage_percentage,
                duration_seconds=new_test_result.duration_seconds,
                error_summary=new_test_result.error_summary[:2000],
                fix_attempt=attempt,
            )
            self.db.add(test_run)
            await self.db.commit()

            await self._broadcast("test_completed", {
                "task_id": task.id,
                "test_type": "unit",
                "passed": new_test_result.passed,
                "total": new_test_result.total_tests,
                "failed": new_test_result.failed_tests,
                "coverage": new_test_result.coverage_percentage,
                "fix_attempt": attempt,
            })

            if new_test_result.passed:
                return new_test_result
            test_result = new_test_result

        return test_result

    async def run_integration_tests(
        self,
        user_story: UserStory,
        feature: Feature,
        execution_run_id: str | None,
    ) -> TestResult:
        await self._broadcast("test_started", {"task_id": user_story.id, "test_type": "integration"})
        await self._broadcast("claude_output", {
            "message": f"Running integration tests for story: {user_story.title}",
        })

        prompt = self.prompt_builder.build_integration_test_prompt(user_story, feature)
        runner = ClaudeRunner(self.workspace, self.budget)

        start_time = datetime.utcnow()
        result = await runner.execute(prompt)
        duration = (datetime.utcnow() - start_time).total_seconds()

        test_result = self._parse_test_result(result.output if result.success else result.error, duration)

        # Use first task's ID as reference
        ref_task_id = user_story.tasks[0].id if user_story.tasks else ""
        test_run = TestRun(
            task_id=ref_task_id,
            execution_run_id=execution_run_id,
            test_type="integration",
            status="passed" if test_result.passed else "failed",
            total_tests=test_result.total_tests,
            passed_tests=test_result.passed_tests,
            failed_tests=test_result.failed_tests,
            coverage_percentage=test_result.coverage_percentage,
            duration_seconds=test_result.duration_seconds,
            error_summary=test_result.error_summary[:2000],
        )
        self.db.add(test_run)
        await self.db.commit()

        await self._broadcast("test_completed", {
            "task_id": user_story.id,
            "test_type": "integration",
            "passed": test_result.passed,
            "total": test_result.total_tests,
            "failed": test_result.failed_tests,
            "coverage": test_result.coverage_percentage,
        })

        return test_result

    async def generate_test_report(
        self,
        execution_run_id: str,
        scope_type: str,
        scope_id: str,
    ) -> TestReport:
        from sqlalchemy import select

        result = await self.db.execute(
            select(TestRun).where(TestRun.execution_run_id == execution_run_id)
        )
        runs = result.scalars().all()

        total = sum(r.total_tests for r in runs)
        passed = sum(r.passed_tests for r in runs)
        failed = sum(r.failed_tests for r in runs)
        coverages = [r.coverage_percentage for r in runs if r.coverage_percentage > 0]
        avg_coverage = sum(coverages) / len(coverages) if coverages else 0.0

        unit_runs = [r for r in runs if r.test_type == "unit"]
        integration_runs = [r for r in runs if r.test_type == "integration"]

        overall_passed = all(r.status == "passed" for r in runs) if runs else False
        integration_passed = all(r.status == "passed" for r in integration_runs) if integration_runs else True

        summary_lines = [
            f"## Test Results {'✅' if overall_passed else '❌'}",
            f"- Total Tests: {total} ({passed} passed, {failed} failed)",
            f"- Code Coverage: {avg_coverage:.1f}%",
            f"- Unit Tests: {'✅ All passed' if all(r.status == 'passed' for r in unit_runs) else '❌ Some failed'}",
            f"- Integration Tests: {'✅ Passed' if integration_passed else '❌ Failed' if integration_runs else '⏭️ Skipped'}",
        ]

        if failed > 0:
            summary_lines.append("\n### Failures:")
            for r in runs:
                if r.status == "failed" and r.error_summary:
                    summary_lines.append(f"- [{r.test_type}] {r.error_summary[:100]}")

        report = TestReport(
            execution_run_id=execution_run_id,
            project_id=self.project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            overall_status="passed" if overall_passed else "failed",
            unit_coverage=avg_coverage,
            integration_passed=integration_passed,
            performance_passed=True,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            report_summary="\n".join(summary_lines),
        )
        self.db.add(report)
        await self.db.commit()

        return report

    def _parse_test_result(self, output: str, duration: float) -> TestResult:
        json_match = re.search(
            r'\{[^{}]*"tests_passed"\s*:\s*(true|false)[^{}]*\}',
            output,
            re.IGNORECASE,
        )

        if json_match:
            try:
                data = json.loads(json_match.group())
                return TestResult(
                    passed=data.get("tests_passed", False),
                    total_tests=data.get("total", 0),
                    passed_tests=data.get("passed", 0),
                    failed_tests=data.get("failed", 0),
                    coverage_percentage=data.get("coverage", 0.0),
                    duration_seconds=duration,
                    error_summary="" if data.get("tests_passed") else self._extract_errors(output),
                    raw_output=output[-3000:],
                )
            except json.JSONDecodeError:
                pass

        # Fallback: assume Claude ran tests but didn't output structured JSON
        has_failures = any(
            marker in output.lower()
            for marker in ["failed", "error", "assertion", "traceback"]
        )

        return TestResult(
            passed=not has_failures,
            total_tests=1,
            passed_tests=0 if has_failures else 1,
            failed_tests=1 if has_failures else 0,
            coverage_percentage=0.0,
            duration_seconds=duration,
            error_summary=self._extract_errors(output) if has_failures else "",
            raw_output=output[-3000:],
        )

    @staticmethod
    def _extract_errors(output: str) -> str:
        lines = output.split("\n")
        error_lines = []
        for line in lines:
            lower = line.lower()
            if "failed" in lower or "error" in lower or "assert" in lower:
                error_lines.append(line.strip())
        return "\n".join(error_lines[:10])

    async def _broadcast(self, event_type: str, payload: dict):
        await ws_manager.broadcast(self.project_id, {"type": event_type, "payload": payload})
