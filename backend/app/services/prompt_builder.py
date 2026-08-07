from app.models.backlog import Feature, UserStory, Task


class PromptBuilder:
    def build_task_prompt(
        self,
        task: Task,
        user_story: UserStory,
        feature: Feature,
        repo_context: str = "",
        requirement_analysis: dict | None = None,
        implementation_plan: dict | None = None,
    ) -> str:
        sections = []

        sections.append("# Code Generation Task\n")
        sections.append(f"## Feature: {feature.title}")
        if feature.description:
            sections.append(f"{feature.description}\n")

        sections.append(f"## User Story: {user_story.title}")
        if user_story.description:
            sections.append(f"{user_story.description}")
        if user_story.acceptance_criteria:
            sections.append(f"\n### Acceptance Criteria:\n{user_story.acceptance_criteria}")

        sections.append(f"\n## Task: {task.title}")
        if task.description:
            sections.append(f"{task.description}")

        # Day 2 — Approved Requirement Contract
        if requirement_analysis:
            sections.append("\n# APPROVED REQUIREMENT CONTRACT")
            summary = requirement_analysis.get("summary", "")
            if summary:
                sections.append(f"\n## Requirement Summary\n{summary}")
            for heading, key in [
                ("Acceptance Criteria", "acceptance_criteria"),
                ("Functional Rules", "functional_rules"),
                ("Edge Cases", "edge_cases"),
                ("Assumptions", "assumptions"),
                ("Dependencies", "dependencies"),
                ("Known Risks", "risks"),
            ]:
                values = requirement_analysis.get(key, [])
                if values:
                    sections.append(
                        f"\n## {heading}\n"
                        + "\n".join(f"- {item}" for item in values)
                    )

        # Day 2 — Approved Implementation Plan
        if implementation_plan:
            sections.append("\n# APPROVED IMPLEMENTATION PLAN")
            sections.append(
                "\n## Plan Summary\n"
                + implementation_plan.get("work_summary", "")
            )
            matching = [
                item
                for item in implementation_plan.get("task_plan", [])
                if item.get("task_id") == task.id
            ]
            if matching:
                item = matching[0]
                sections.append(
                    "\n## Current Task Execution Order\n"
                    + str(item.get("execution_order", ""))
                )
                sections.append(
                    "\n## Current Task Approach\n"
                    + item.get("approach", "")
                )
                files = item.get("related_files", [])
                if files:
                    sections.append(
                        "\n## Related Files\n"
                        + "\n".join(f"- {path}" for path in files)
                    )
            changes = implementation_plan.get("planned_changes", [])
            if changes:
                sections.append("\n## Planned Repository Changes")
                for change in changes:
                    sections.append(
                        "- "
                        + change.get("action", "inspect").upper()
                        + " "
                        + change.get("path", "")
                        + ": "
                        + change.get("purpose", "")
                    )

        sections.append("\n## Instructions")
        sections.append(
            "Implement the task described above. Follow these guidelines:\n"
            "- Write clean, well-structured code\n"
            "- Follow existing code conventions in the repository\n"
            "- Create any necessary files and directories\n"
            "- Ensure the code is functional and complete\n"
            "- Do not leave placeholder or TODO comments\n"
        )

        if repo_context:
            sections.append(f"\n## Repository Context\n{repo_context}")

        # Day 2 implementation rules
        sections.append(
            "# AEGIS DAY 2 IMPLEMENTATION RULES\n"
            "- The approved Requirement Contract is authoritative.\n"
            "- Follow the approved Implementation Plan.\n"
            "- Implement only the current imported task.\n"
            "- Inspect existing code before creating replacements.\n"
            "- Reuse existing modules when appropriate.\n"
            "- Do not modify unrelated files.\n"
            "- Preserve architecture and naming conventions.\n"
            "- Implement approved validation and edge cases.\n"
            "- Do not weaken acceptance criteria or existing tests."
        )

        return "\n".join(sections)

    def build_test_prompt(
        self,
        task: Task,
        modified_files: list[str],
        test_type: str = "unit",
    ) -> str:
        sections = []
        sections.append("# Test Generation & Execution\n")
        sections.append(f"## Task Implemented: {task.title}")
        if task.description:
            sections.append(f"{task.description}")

        sections.append("\n## Files Created/Modified:")
        for f in modified_files:
            sections.append(f"- {f}")

        if test_type == "unit":
            sections.append("\n## Instructions")
            sections.append(
                "Write and run comprehensive unit tests for the code listed above.\n\n"
                "Steps:\n"
                "1. Examine the implementation files to understand what was built\n"
                "2. Create test files following the project's testing conventions:\n"
                "   - For Python: use pytest. Place tests in a `tests/` directory.\n"
                "   - For Vue/JS: use Vitest. Place tests alongside components or in `__tests__/`.\n"
                "3. Write tests covering:\n"
                "   - Happy path (normal expected behavior)\n"
                "   - Edge cases (empty inputs, boundary values)\n"
                "   - Error cases (invalid inputs, missing data)\n"
                "4. Run the tests:\n"
                "   - Python: `pytest --tb=short -v`\n"
                "   - Frontend: `npx vitest run`\n"
                "5. Ensure all tests PASS. If any fail, fix the IMPLEMENTATION code (not the tests) and re-run.\n\n"
                "After all tests pass, output a JSON summary on the LAST line of your response in this exact format:\n"
                '```json\n'
                '{"tests_passed": true, "total": 10, "passed": 10, "failed": 0, "coverage": 85.5}\n'
                '```\n'
                "If tests fail after your fixes, still output the JSON with tests_passed: false and include error details."
            )

        elif test_type == "integration":
            sections.append("\n## Instructions")
            sections.append(
                "Write and run integration tests that verify the components work together.\n\n"
                "Steps:\n"
                "1. Examine all files in the project to understand the full feature\n"
                "2. Write integration tests that:\n"
                "   - Test API endpoints end-to-end (request → response)\n"
                "   - Test database operations (create, read, update, delete)\n"
                "   - Test component interactions\n"
                "3. Run tests: `pytest tests/ --tb=short -v`\n"
                "4. Fix any failures in the implementation code.\n\n"
                "Output JSON summary on the last line:\n"
                '```json\n'
                '{"tests_passed": true, "total": 5, "passed": 5, "failed": 0, "coverage": 78.0}\n'
                '```'
            )

        elif test_type == "performance":
            sections.append("\n## Instructions")
            sections.append(
                "Write and run performance tests for the API endpoints.\n\n"
                "Steps:\n"
                "1. Create a simple load test script using Python's `time` module or `locust`\n"
                "2. Test key endpoints with:\n"
                "   - Response time measurement (average, p95)\n"
                "   - Concurrent request handling (10 simultaneous requests)\n"
                "3. Acceptance criteria:\n"
                "   - Average response time < 500ms\n"
                "   - p95 response time < 1000ms\n"
                "   - No errors under 10 concurrent requests\n"
                "4. Run the performance tests\n\n"
                "Output JSON summary on the last line:\n"
                '```json\n'
                '{"tests_passed": true, "total": 3, "passed": 3, "failed": 0, "avg_response_ms": 120, "p95_response_ms": 250}\n'
                '```'
            )

        return "\n".join(sections)

    def build_fix_prompt(
        self,
        task: Task,
        test_output: str,
        modified_files: list[str],
        attempt: int = 1,
    ) -> str:
        sections = []
        sections.append(f"# Fix Failing Tests (Attempt {attempt})\n")
        sections.append(f"## Task: {task.title}")

        sections.append("\n## Test Failures:")
        sections.append(f"```\n{test_output[:3000]}\n```")

        sections.append("\n## Files to Fix:")
        for f in modified_files:
            sections.append(f"- {f}")

        sections.append("\n## Instructions")
        sections.append(
            "The tests above are CORRECT — they test the expected behavior.\n"
            "Fix the IMPLEMENTATION code (not the tests) to make all tests pass.\n\n"
            "Steps:\n"
            "1. Read the failing test assertions to understand what's expected\n"
            "2. Read the implementation code to find the bug\n"
            "3. Fix the implementation\n"
            "4. Re-run the tests: `pytest --tb=short -v`\n"
            "5. Repeat until all tests pass\n\n"
            "After all tests pass, output JSON summary on the last line:\n"
            '```json\n'
            '{"tests_passed": true, "total": 10, "passed": 10, "failed": 0, "coverage": 85.5}\n'
            '```'
        )

        return "\n".join(sections)

    def build_integration_test_prompt(
        self,
        user_story: UserStory,
        feature: Feature,
    ) -> str:
        sections = []
        sections.append("# Integration Test Generation\n")
        sections.append(f"## Feature: {feature.title}")
        sections.append(f"## User Story: {user_story.title}")
        if user_story.acceptance_criteria:
            sections.append(f"\n### Acceptance Criteria:\n{user_story.acceptance_criteria}")

        sections.append("\n## Tasks Completed:")
        for t in user_story.tasks:
            sections.append(f"- {t.title}")

        sections.append("\n## Instructions")
        sections.append(
            "Write integration tests that verify this entire user story works end-to-end.\n\n"
            "These tests should verify the acceptance criteria are met by:\n"
            "1. Testing the full request/response cycle through API endpoints\n"
            "2. Verifying database state after operations\n"
            "3. Testing error handling and edge cases\n"
            "4. Testing the interaction between components\n\n"
            "Run all tests: `pytest --tb=short -v`\n"
            "Fix any implementation issues found.\n\n"
            "Output JSON summary on the last line:\n"
            '```json\n'
            '{"tests_passed": true, "total": 8, "passed": 8, "failed": 0, "coverage": 80.0}\n'
            '```'
        )

        return "\n".join(sections)

    def build_continuation_prompt(
        self,
        task: Task,
        previous_output: str,
        modified_files: list[str],
    ) -> str:
        sections = []
        sections.append("# Continue Previous Task\n")
        sections.append(f"## Task: {task.title}")
        if task.description:
            sections.append(f"{task.description}")

        sections.append("\n## Previous Progress")
        sections.append("The following files were already modified:")
        for f in modified_files:
            sections.append(f"- {f}")

        if previous_output:
            sections.append(f"\n## Previous Output (summary)\n{previous_output[:2000]}")

        sections.append(
            "\n## Instructions\n"
            "Continue the implementation from where it left off. "
            "The files listed above already have partial changes. "
            "Complete the remaining work for this task."
        )

        return "\n".join(sections)

    def build_regression_test_prompt(self) -> str:
        sections = []
        sections.append("# Regression Testing — Full Codebase\n")
        sections.append("## Instructions")
        sections.append(
            "Run a full regression test suite on this codebase.\n\n"
            "Steps:\n"
            "1. Discover the project structure — identify the language(s) and frameworks used\n"
            "2. Check if tests already exist (look for `tests/`, `__tests__/`, `*_test.py`, `*.spec.ts`, etc.)\n"
            "3. If existing tests are found:\n"
            "   - Run them: `pytest --tb=short -v` (Python) or `npx vitest run` (JS/TS)\n"
            "   - If any fail, fix the IMPLEMENTATION code (not the tests) and re-run\n"
            "4. If no tests exist OR coverage is below 60%:\n"
            "   - Generate comprehensive tests for all major modules/endpoints\n"
            "   - Run them and fix any failures in the implementation\n"
            "5. Measure coverage: `pytest --cov --tb=short -v` or `npx vitest run --coverage`\n\n"
            "After all tests pass, output a JSON summary on the LAST line of your response:\n"
            '```json\n'
            '{"tests_passed": true, "total": 25, "passed": 25, "failed": 0, "coverage": 82.0}\n'
            '```\n'
            "If tests fail after your fixes, still output the JSON with tests_passed: false."
        )
        return "\n".join(sections)

    def build_pr_test_prompt(self, changed_files: list[str], branch: str) -> str:
        sections = []
        sections.append(f"# PR Branch Testing — {branch}\n")
        sections.append("## Changed Files:")
        for f in changed_files:
            sections.append(f"- {f}")

        sections.append("\n## Instructions")
        sections.append(
            "Generate and run tests specifically for the files changed in this PR branch.\n\n"
            "Steps:\n"
            "1. Read each changed file listed above to understand what was implemented\n"
            "2. Write targeted tests for the new/modified code:\n"
            "   - Unit tests for new functions, classes, endpoints\n"
            "   - Integration tests if the changes involve multiple components\n"
            "3. Also run any existing tests that might be affected by these changes\n"
            "4. Run all tests: `pytest --tb=short -v` (Python) or `npx vitest run` (JS/TS)\n"
            "5. If any test fails, fix the IMPLEMENTATION code (not the tests) and re-run\n\n"
            "After all tests pass, output a JSON summary on the LAST line of your response:\n"
            '```json\n'
            '{"tests_passed": true, "total": 12, "passed": 12, "failed": 0, "coverage": 75.0}\n'
            '```\n'
            "If tests fail after your fixes, still output the JSON with tests_passed: false."
        )
        return "\n".join(sections)

    def build_manual_fix_prompt(self, test_output: str, scope: str, attempt: int) -> str:
        sections = []
        sections.append(f"# Fix Failing Tests (Attempt {attempt}) — {scope} testing\n")
        sections.append("## Test Failures:")
        sections.append(f"```\n{test_output[:3000]}\n```")
        sections.append("\n## Instructions")
        sections.append(
            "The tests above are CORRECT — they test the expected behavior.\n"
            "Fix the IMPLEMENTATION code (not the tests) to make all tests pass.\n\n"
            "Steps:\n"
            "1. Read the failing test assertions to understand what's expected\n"
            "2. Read the implementation code to find the bug\n"
            "3. Fix the implementation\n"
            "4. Re-run the tests: `pytest --tb=short -v`\n"
            "5. Repeat until all tests pass\n\n"
            "After all tests pass, output JSON summary on the last line:\n"
            '```json\n'
            '{"tests_passed": true, "total": 10, "passed": 10, "failed": 0, "coverage": 85.5}\n'
            '```'
        )
        return "\n".join(sections)

    def build_verification_prompt(self, task: Task, modified_files: list[str]) -> str:
        return (
            f"Verify that the task '{task.title}' has been fully implemented.\n"
            f"Modified files: {', '.join(modified_files)}\n\n"
            "Check:\n"
            "1. All requirements from the task description are met\n"
            "2. The code compiles/runs without errors\n"
            "3. No placeholder or TODO items remain\n\n"
            "Respond with COMPLETE if the task is done, or INCOMPLETE with details of what's missing."
        )
