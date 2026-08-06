import json
import logging
import re
import subprocess
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.testing import TestRun, TestReport
from app.services.claude_runner import ClaudeRunner
from app.services.prompt_builder import PromptBuilder
from app.services.test_runner import TestResult
from app.services.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 3


class ManualTestService:
    def __init__(self, project: Project, db: AsyncSession):
        self.project = project
        self.project_id = project.id
        self.db = db
        self.workspace = project.workspace_path
        self.budget = project.claude_max_budget_usd
        self.prompt_builder = PromptBuilder()

    async def run(self, scope: str, branch: str | None, test_types: list[str]) -> TestReport:
        await self._broadcast("claude_output", {"message": f"Manual test triggered: scope={scope}, branch={branch}"})

        if scope == "pr":
            changed_files = await self._get_changed_files(branch)
            if not changed_files:
                await self._broadcast("claude_output", {"message": "No changed files found on branch. Running full test suite instead."})
                scope = "regression"

        if scope == "regression":
            test_result = await self._run_regression_tests(test_types)
        else:
            test_result = await self._run_pr_tests(branch, changed_files, test_types)

        if not test_result.passed:
            test_result = await self._fix_loop(test_result, scope)

        report = await self._create_report(test_result, scope, branch)
        await self._broadcast("claude_output", {"message": f"Manual testing complete: {'PASSED' if test_result.passed else 'FAILED'}"})
        return report

    async def _run_regression_tests(self, test_types: list[str]) -> TestResult:
        await self._broadcast("test_started", {"task_id": "manual", "test_type": "regression"})

        prompt = self.prompt_builder.build_regression_test_prompt()
        runner = ClaudeRunner(self.workspace, self.budget)

        start_time = datetime.utcnow()
        result = await runner.execute(prompt)
        duration = (datetime.utcnow() - start_time).total_seconds()

        test_result = self._parse_test_result(result.output if result.success else result.error, duration)

        test_run = TestRun(
            task_id="manual-regression",
            execution_run_id=None,
            test_type="regression",
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
            "task_id": "manual",
            "test_type": "regression",
            "passed": test_result.passed,
            "total": test_result.total_tests,
            "failed": test_result.failed_tests,
            "coverage": test_result.coverage_percentage,
        })

        return test_result

    async def _run_pr_tests(self, branch: str, changed_files: list[str], test_types: list[str]) -> TestResult:
        await self._broadcast("test_started", {"task_id": "manual", "test_type": "pr"})

        prompt = self.prompt_builder.build_pr_test_prompt(changed_files, branch or "current")
        runner = ClaudeRunner(self.workspace, self.budget)

        start_time = datetime.utcnow()
        result = await runner.execute(prompt)
        duration = (datetime.utcnow() - start_time).total_seconds()

        test_result = self._parse_test_result(result.output if result.success else result.error, duration)

        test_run = TestRun(
            task_id="manual-pr",
            execution_run_id=None,
            test_type="pr",
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
            "task_id": "manual",
            "test_type": "pr",
            "passed": test_result.passed,
            "total": test_result.total_tests,
            "failed": test_result.failed_tests,
            "coverage": test_result.coverage_percentage,
        })

        return test_result

    async def _fix_loop(self, test_result: TestResult, scope: str) -> TestResult:
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            if test_result.passed:
                break

            await self._broadcast("fix_attempt", {
                "task_id": "manual",
                "attempt": attempt,
                "reason": test_result.error_summary[:200],
            })

            fix_prompt = self.prompt_builder.build_manual_fix_prompt(
                test_result.raw_output, scope, attempt
            )
            runner = ClaudeRunner(self.workspace, self.budget)

            start_time = datetime.utcnow()
            fix_result = await runner.execute(fix_prompt)
            duration = (datetime.utcnow() - start_time).total_seconds()

            test_result = self._parse_test_result(
                fix_result.output if fix_result.success else fix_result.error, duration
            )

            test_run = TestRun(
                task_id=f"manual-{scope}",
                execution_run_id=None,
                test_type=scope,
                status="passed" if test_result.passed else "failed",
                total_tests=test_result.total_tests,
                passed_tests=test_result.passed_tests,
                failed_tests=test_result.failed_tests,
                coverage_percentage=test_result.coverage_percentage,
                duration_seconds=test_result.duration_seconds,
                error_summary=test_result.error_summary[:2000],
                fix_attempt=attempt,
            )
            self.db.add(test_run)
            await self.db.commit()

            await self._broadcast("test_completed", {
                "task_id": "manual",
                "test_type": scope,
                "passed": test_result.passed,
                "total": test_result.total_tests,
                "failed": test_result.failed_tests,
                "coverage": test_result.coverage_percentage,
                "fix_attempt": attempt,
            })

        return test_result

    async def _get_changed_files(self, branch: str | None) -> list[str]:
        import asyncio

        target_branch = branch or "HEAD"
        cmd = f"git diff main...{target_branch} --name-only"

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=self.workspace,
                shell=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception as e:
            logger.warning(f"Failed to get changed files: {e}")

        return []

    async def _create_report(self, test_result: TestResult, scope: str, branch: str | None) -> TestReport:
        overall_passed = test_result.passed
        scope_label = f"regression" if scope == "regression" else f"pr:{branch or 'current'}"

        summary_lines = [
            f"## Manual Test Results {'✅' if overall_passed else '❌'}",
            f"- Scope: {scope_label}",
            f"- Total Tests: {test_result.total_tests} ({test_result.passed_tests} passed, {test_result.failed_tests} failed)",
            f"- Code Coverage: {test_result.coverage_percentage:.1f}%",
        ]

        if not overall_passed and test_result.error_summary:
            summary_lines.append(f"\n### Errors:\n{test_result.error_summary[:500]}")

        report = TestReport(
            execution_run_id=None,
            project_id=self.project_id,
            scope_type=scope,
            scope_id=branch or "all",
            overall_status="passed" if overall_passed else "failed",
            unit_coverage=test_result.coverage_percentage,
            integration_passed=overall_passed,
            performance_passed=True,
            total_tests=test_result.total_tests,
            passed_tests=test_result.passed_tests,
            failed_tests=test_result.failed_tests,
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
