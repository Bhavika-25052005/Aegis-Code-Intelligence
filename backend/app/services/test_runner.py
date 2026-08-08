import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

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

    def detect_test_framework(self) -> Optional[str]:
        """Detect the project's test runner command. Returns None if nothing found."""
        workspace = Path(self.workspace)
        # Python
        if (workspace / "pytest.ini").exists() or (workspace / "setup.cfg").exists() or (workspace / "pyproject.toml").exists():
            return "pytest"
        if any(workspace.rglob("test_*.py")) or any(workspace.rglob("*_test.py")):
            return "pytest"
        # JavaScript / TypeScript
        pkg = workspace / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    return f"npm test"
            except Exception:
                pass
        # Java
        if (workspace / "gradlew").exists():
            return "./gradlew test"
        if (workspace / "pom.xml").exists():
            return "mvn test"
        # .NET
        if any(workspace.rglob("*.csproj")):
            return "dotnet test"
        return None

    def run_test_files_sync(self, explicit_files: list[str]) -> TestResult:
        """Run explicit test files using the detected framework. Returns a TestResult."""
        import sys

        framework = self.detect_test_framework()
        if not framework:
            return TestResult(
                passed=False,
                error_summary="No runnable test framework detected. Needs Human Review.",
                raw_output="No test framework found in workspace.",
            )
        workspace = str(self.workspace)

        # Always use the same Python interpreter that is running Aegis so the
        # workspace's installed packages are available to the tests.
        python_exe = sys.executable

        if framework == "pytest":
            base = [python_exe, "-m", "pytest", f"--rootdir={workspace}", "--tb=short", "-v", "--no-header"]
            if explicit_files:
                cmd = base + explicit_files
            else:
                cmd = base
        elif framework.startswith("npm"):
            cmd = ["npm", "test", "--", "--run"]
        elif framework == "./gradlew test":
            cmd = ["./gradlew", "test"]
        elif framework == "mvn test":
            cmd = ["mvn", "test"]
        elif framework == "dotnet test":
            cmd = ["dotnet", "test"]
        else:
            cmd = framework.split()

        logger.info(f"Running test command: {cmd} in {workspace}")
        start = datetime.utcnow()

        # Inject workspace root into PYTHONPATH so imports like
        # `from backend.api.routes.patients import ...` resolve correctly
        env = os.environ.copy()
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = workspace + (os.pathsep + existing_path if existing_path else "")

        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            duration = (datetime.utcnow() - start).total_seconds()
            output = (proc.stdout or "") + (proc.stderr or "")

            # Parse pytest summary line: "X passed", "X failed", "X error"
            total, passed_count, failed_count = self._parse_pytest_counts(output)

            # Exit code 0 = all passed; 1 = some failed; 5 = no tests collected
            if proc.returncode == 5 or (proc.returncode == 0 and total == 0):
                # No tests collected — treat as needs-review not auto-pass
                return TestResult(
                    passed=False,
                    total_tests=0,
                    passed_tests=0,
                    failed_tests=0,
                    duration_seconds=duration,
                    error_summary="No tests were collected. Check test file paths and imports.",
                    raw_output=output[-4000:],
                )

            run_passed = proc.returncode == 0
            return TestResult(
                passed=run_passed,
                total_tests=total,
                passed_tests=passed_count,
                failed_tests=failed_count,
                duration_seconds=duration,
                error_summary="" if run_passed else self._extract_errors(output),
                raw_output=output[-4000:],
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                passed=False,
                error_summary="Test run timed out.",
                raw_output="Test run timed out after 300s.",
            )
        except Exception as exc:
            return TestResult(
                passed=False,
                error_summary=str(exc),
                raw_output=str(exc),
            )

    async def run_unit_tests(
        self,
        task: Task,
        execution_run_id: str | None,
        modified_files: list[str],
        explicit_files: Optional[list[str]] = None,
    ) -> TestResult:
        await self._broadcast("test_started", {"task_id": task.id, "test_type": "unit"})
        await self._broadcast("test_generation_started", {"task_id": task.id, "test_type": "unit"})

        # When explicit generated test files are provided, run them directly first
        if explicit_files:
            await self._broadcast("test_run_started", {"task_id": task.id, "files": explicit_files})
            native_result = await asyncio.get_event_loop().run_in_executor(
                None, self.run_test_files_sync, explicit_files
            )
            if native_result.total_tests > 0 or not native_result.passed:
                test_run = TestRun(
                    task_id=task.id,
                    execution_run_id=execution_run_id,
                    test_type="unit",
                    status="passed" if native_result.passed else "failed",
                    total_tests=native_result.total_tests,
                    passed_tests=native_result.passed_tests,
                    failed_tests=native_result.failed_tests,
                    coverage_percentage=native_result.coverage_percentage,
                    duration_seconds=native_result.duration_seconds,
                    error_summary=native_result.error_summary[:2000],
                    fix_attempt=0,
                )
                self.db.add(test_run)
                await self.db.commit()
                await self._broadcast("test_result", {
                    "task_id": task.id,
                    "test_type": "unit",
                    "passed": native_result.passed,
                    "total": native_result.total_tests,
                    "failed": native_result.failed_tests,
                })
                await self._broadcast("test_completed", {
                    "task_id": task.id,
                    "test_type": "unit",
                    "passed": native_result.passed,
                    "total": native_result.total_tests,
                    "failed": native_result.failed_tests,
                    "coverage": native_result.coverage_percentage,
                })
                return native_result

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

    async def fix_with_requirement_context(
        self,
        task: Task,
        user_story: UserStory,
        feature: Feature,
        execution_run_id: str | None,
        test_result: TestResult,
        requirement_analysis: dict,
        implementation_plan: dict,
        failing_tests: list[dict],
        modified_files: list[str],
        explicit_files: Optional[list[str]] = None,
    ) -> TestResult:
        """Day 3 repair loop: uses the full requirement contract in the fix prompt."""
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            await self._broadcast("repair_started", {
                "task_id": task.id,
                "attempt": attempt,
                "reason": test_result.error_summary[:200],
            })
            await self._broadcast("claude_output", {
                "message": f"Repair attempt {attempt}/{MAX_FIX_ATTEMPTS} for: {task.title}",
            })

            repair_prompt = self.prompt_builder.build_test_repair_prompt(
                task=task,
                user_story=user_story,
                feature=feature,
                requirement_analysis=requirement_analysis,
                implementation_plan=implementation_plan,
                failing_tests=failing_tests,
                test_output=test_result.raw_output,
                attempt=attempt,
            )
            runner = ClaudeRunner(self.workspace, self.budget)
            fix_result = await runner.execute(repair_prompt)

            start_time = datetime.utcnow()
            duration = (datetime.utcnow() - start_time).total_seconds()

            # After repair, re-run tests
            if explicit_files:
                new_test_result = await asyncio.get_event_loop().run_in_executor(
                    None, self.run_test_files_sync, explicit_files
                )
            else:
                new_test_result = self._parse_test_result(
                    fix_result.output if fix_result.success else fix_result.error, duration
                )

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

            await self._broadcast("repair_result", {
                "task_id": task.id,
                "attempt": attempt,
                "passed": new_test_result.passed,
            })
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

    def find_regression_tests(self) -> list[str]:
        """Return test files from tests/regression if the folder exists, else empty list."""
        regression_dir = Path(self.workspace) / "tests" / "regression"
        if not regression_dir.exists() or not regression_dir.is_dir():
            return []
        files = [
            str(f) for f in regression_dir.rglob("test_*.py")
        ] + [
            str(f) for f in regression_dir.rglob("*_test.py")
        ]
        return sorted(set(files))

    async def run_story_quality_gate(
        self,
        user_story: UserStory,
        feature: Feature,
        execution_run_id: str | None,
        requirement_analysis: dict,
        implementation_plan: dict,
        generated_files: list[str],
        include_existing_regression: bool = True,
    ) -> TestResult:
        """Quality gate: run generated integration/system tests + existing regression suite."""
        await self._broadcast("story_quality_gate", {
            "story_id": user_story.id,
            "status": "started",
            "generated_files": generated_files,
        })
        await self._broadcast("claude_output", {
            "message": f"Quality gate starting for '{user_story.title}'",
        })

        # ── Part 1: Claude runs the generated integration/system test files ──────
        prompt = self.prompt_builder.build_story_quality_gate_prompt(
            user_story=user_story,
            feature=feature,
            requirement_analysis=requirement_analysis,
            implementation_plan=implementation_plan,
            generated_files=generated_files,
        )
        runner = ClaudeRunner(self.workspace, self.budget)

        await self._broadcast("claude_output", {
            "message": "Quality gate — running integration/system tests...",
        })
        start_time = datetime.utcnow()
        result = await runner.execute(prompt)
        duration = (datetime.utcnow() - start_time).total_seconds()
        integ_result = self._parse_test_result(
            result.output if result.success else result.error, duration
        )

        # ── Part 2: Existing regression suite (tests/regression/) ─────────────
        regression_files = self.find_regression_tests() if include_existing_regression else []
        reg_total = reg_passed = reg_failed = 0
        reg_errors = ""

        if regression_files:
            await self._broadcast("claude_output", {
                "message": f"Quality gate — running {len(regression_files)} existing regression test(s)...",
            })
            reg_result = await asyncio.get_event_loop().run_in_executor(
                None, self.run_test_files_sync, regression_files
            )
            reg_total   = reg_result.total_tests
            reg_passed  = reg_result.passed_tests
            reg_failed  = reg_result.failed_tests
            reg_errors  = reg_result.error_summary
            await self._broadcast("claude_output", {
                "message": (
                    f"Regression: {reg_passed}/{reg_total} passed"
                    + (f" — {reg_errors[:120]}" if reg_errors else "")
                ),
            })
        else:
            await self._broadcast("claude_output", {
                "message": "Regression: no tests/regression folder found — skipped (0 tests)",
            })

        # ── Combine both results ───────────────────────────────────────────────
        total_tests   = integ_result.total_tests + reg_total
        passed_tests  = integ_result.passed_tests + reg_passed
        failed_tests  = integ_result.failed_tests + reg_failed
        combined_pass = integ_result.passed and reg_failed == 0
        error_summary = " | ".join(filter(None, [integ_result.error_summary, reg_errors]))

        combined = TestResult(
            passed=combined_pass,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            coverage_percentage=integ_result.coverage_percentage,
            duration_seconds=integ_result.duration_seconds + (reg_result.duration_seconds if regression_files else 0),
            error_summary=error_summary[:2000],
            raw_output=integ_result.raw_output,
        )

        ref_task_id = user_story.tasks[0].id if user_story.tasks else user_story.id
        test_run = TestRun(
            task_id=ref_task_id,
            execution_run_id=execution_run_id,
            test_type="quality",
            status="passed" if combined.passed else "failed",
            total_tests=combined.total_tests,
            passed_tests=combined.passed_tests,
            failed_tests=combined.failed_tests,
            coverage_percentage=combined.coverage_percentage,
            duration_seconds=combined.duration_seconds,
            error_summary=combined.error_summary[:2000],
        )
        self.db.add(test_run)
        await self.db.commit()

        await self._broadcast("story_quality_gate", {
            "story_id": user_story.id,
            "status": "passed" if combined.passed else "failed",
            "total": combined.total_tests,
            "failed": combined.failed_tests,
            "regression_total": reg_total,
            "regression_skipped": regression_files == [],
        })
        await self._broadcast("test_completed", {
            "task_id": user_story.id,
            "test_type": "quality",
            "passed": combined.passed,
            "total": combined.total_tests,
            "failed": combined.failed_tests,
            "coverage": combined.coverage_percentage,
        })

        return combined

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
    def _parse_pytest_counts(output: str) -> tuple[int, int, int]:
        """Parse pytest summary line and return (total, passed, failed)."""
        # Matches lines like: "5 passed", "3 failed", "2 passed, 1 failed", "73 passed in 1.16s"
        passed = 0
        failed = 0
        errors = 0

        passed_match = re.search(r'(\d+)\s+passed', output)
        failed_match = re.search(r'(\d+)\s+failed', output)
        error_match  = re.search(r'(\d+)\s+error', output)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if error_match:
            errors = int(error_match.group(1))

        total = passed + failed + errors
        return total, passed, failed + errors

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
