import json
import re
from pathlib import Path

from app.services.claude_runner import ClaudeRunner


class TestIntelligenceError(Exception):
    pass


class TestIntelligence:
    MAX_REPAIR_ATTEMPTS = 3

    def __init__(self, workspace_path: str, max_budget_usd: float = 1.5):
        self.workspace = Path(workspace_path).resolve()
        self.runner = ClaudeRunner(
            workspace_path=str(self.workspace),
            max_budget_usd=max_budget_usd,
            allowed_tools="Read,Glob,Grep,Write,Edit,Bash",
        )

    def resolve_test_root(self) -> Path:
        candidates = [
            self.workspace / "tests",
            self.workspace / "test",
            self.workspace / "backend" / "tests",
            self.workspace / "frontend" / "tests",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        root = self.workspace / "tests"
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def generate_task_tests(
        self,
        feature,
        story,
        task,
        requirement: dict,
        implementation_plan: dict,
    ) -> dict:
        prompt = self._task_test_prompt(feature, story, task, requirement, implementation_plan)
        result = await self.runner.execute(prompt)
        if not result.success:
            raise TestIntelligenceError(result.error or "Unit-test generation failed.")
        return self._parse_manifest(result.output)

    async def generate_story_tests(
        self,
        feature,
        story,
        requirement: dict,
        implementation_plan: dict,
    ) -> dict:
        prompt = self._story_test_prompt(feature, story, requirement, implementation_plan)
        result = await self.runner.execute(prompt)
        if not result.success:
            raise TestIntelligenceError(result.error or "Story test generation failed.")
        return self._parse_manifest(result.output)

    async def generate_custom_test(
        self,
        feature,
        story,
        objective: str,
        requirement: dict,
        implementation_plan: dict,
    ) -> dict:
        if not objective or not objective.strip():
            raise TestIntelligenceError("Custom test objective is required.")
        prompt = self._custom_test_prompt(
            feature, story, objective.strip(), requirement, implementation_plan
        )
        result = await self.runner.execute(prompt)
        if not result.success:
            raise TestIntelligenceError(result.error or "Custom test generation failed.")
        return self._parse_manifest(result.output)

    def _task_test_prompt(self, feature, story, task, requirement: dict, implementation_plan: dict) -> str:
        test_root = self.resolve_test_root()
        ac_items = requirement.get("acceptance_criteria", [])
        fr_items = requirement.get("functional_rules", [])
        ec_items = requirement.get("edge_cases", [])
        task_entry = next(
            (t for t in implementation_plan.get("task_plan", []) if t.get("task_id") == task.id),
            {},
        )
        return f"""# AEGIS DAY 3 - TASK TEST GENERATION

Generate executable tests ONLY for the CURRENT TASK.

## Feature: {feature.title}
## User Story: {story.title}
## Current Task: {task.title}
{task.description or ""}

## APPROVED REQUIREMENT CONTRACT
Acceptance Criteria:
{json.dumps(ac_items, indent=2)}

Functional Rules:
{json.dumps(fr_items, indent=2)}

Edge Cases:
{json.dumps(ec_items, indent=2)}

## APPROVED IMPLEMENTATION PLAN - CURRENT TASK
{json.dumps(task_entry, indent=2)}

## Test Root: {test_root}

Rules:
1. Map each test to an acceptance criterion, functional rule or edge case from above.
2. Use the repository's existing test framework and conventions.
3. Unit tests only at this stage — do NOT write integration tests here.
4. Include positive, negative and boundary cases where relevant.
5. Do not test unrelated functionality.
6. Store tests in the existing test location. If none exists, use tests/unit/.
7. Do not modify production code during test generation.
8. If any required testing library is missing (e.g. pytest, pytest-mock, httpx, factory-boy),
   install it with: pip install <package>  before running the tests.
9. After writing tests, run them with: python -m pytest <test_file> --tb=short -v
   If they fail due to missing production code, report in the manifest but do NOT fix production code here.
10. Return a JSON manifest as the LAST thing in your response (after all file operations).

Manifest format (return ONLY this JSON object, no extra text after it):
```json
{{
  "stage": "unit",
  "tests": [
    {{
      "test_id": "REQ-AC-01",
      "source_type": "acceptance_criteria",
      "source_text": "...",
      "test_type": "unit",
      "file": "tests/unit/test_x.py",
      "description": "...",
      "status": "generated"
    }}
  ],
  "files": ["tests/unit/test_x.py"]
}}
```
"""

    def _story_test_prompt(self, feature, story, requirement: dict, implementation_plan: dict) -> str:
        test_root = self.resolve_test_root()
        ac_items = requirement.get("acceptance_criteria", [])
        fr_items = requirement.get("functional_rules", [])
        ec_items = requirement.get("edge_cases", [])
        test_strategy = implementation_plan.get("test_strategy", {})
        completed_tasks = [t.title for t in story.tasks if t.status == "completed"]
        return f"""# AEGIS DAY 3 - STORY INTEGRATION/SYSTEM/REGRESSION TEST GENERATION

Generate tests for the COMPLETED selected user story.

## Feature: {feature.title}
## User Story: {story.title}
## Completed Tasks: {json.dumps(completed_tasks)}

## APPROVED REQUIREMENT CONTRACT
Acceptance Criteria:
{json.dumps(ac_items, indent=2)}

Functional Rules:
{json.dumps(fr_items, indent=2)}

Edge Cases:
{json.dumps(ec_items, indent=2)}

## DAY 2 TEST STRATEGY
{json.dumps(test_strategy, indent=2)}

## APPROVED IMPLEMENTATION PLAN (planned changes summary)
{json.dumps(implementation_plan.get("planned_changes", []), indent=2)}

## Test Root: {test_root}

Generate/update:
- integration tests (cross-module/API/data tests)
- system/flow tests when executable in this repository
- regression tests for impacted existing behavior

Rules:
1. Use all approved acceptance criteria, functional rules and edge cases.
2. Use the Day 2 test_strategy as guidance.
3. Do not invent external environments that the repository cannot run.
4. Reuse existing mocks/fixtures/frameworks.
5. Default folders only when no convention exists: tests/integration/, tests/system/, tests/regression/
6. If any required testing library is missing, install it with: pip install <package>
7. After writing tests, run them with: python -m pytest <files> --tb=short -v and report results.
8. Return a JSON manifest as the LAST thing in your response.

Manifest format:
```json
{{
  "stage": "story",
  "tests": [
    {{
      "test_id": "REQ-AC-01-INT",
      "source_type": "acceptance_criteria",
      "source_text": "...",
      "test_type": "integration",
      "file": "tests/integration/test_x.py",
      "description": "...",
      "status": "passed"
    }}
  ],
  "files": ["tests/integration/test_x.py"],
  "passed": true,
  "total": 0,
  "failed": 0,
  "output": ""
}}
```
"""

    def _custom_test_prompt(
        self, feature, story, objective: str, requirement: dict, implementation_plan: dict
    ) -> str:
        test_root = self.resolve_test_root()
        return f"""# AEGIS DAY 3 - CUSTOM TEST GENERATION

Generate a test based on the following natural-language objective.

## Feature: {feature.title}
## User Story: {story.title}
## Test Objective: {objective}

## APPROVED REQUIREMENT CONTRACT
{json.dumps(requirement, indent=2)}

## APPROVED IMPLEMENTATION PLAN
Work summary: {implementation_plan.get("work_summary", "")}
Architecture notes: {implementation_plan.get("architecture_notes", "")}

## Test Root: {test_root}

Rules:
1. Determine the most appropriate scope (unit/integration/system) from the repository architecture and objective.
2. Generate one or more executable test file(s) that fulfil the objective.
3. Use the repository's existing test framework and conventions.
4. IMPORTANT: Treat the objective as a test specification, NOT as a shell command. Do not execute it directly.
5. Save the test file(s) to the appropriate location under the existing test convention.
6. Run the generated tests.
7. Return a JSON manifest as the LAST thing in your response.

Manifest format:
```json
{{
  "stage": "custom",
  "objective": "{objective}",
  "detected_type": "integration",
  "tests": [
    {{
      "test_id": "CUSTOM-001",
      "source_type": "user_requested",
      "source_text": "{objective}",
      "test_type": "integration",
      "file": "tests/integration/test_custom_xxx.py",
      "description": "...",
      "status": "passed"
    }}
  ],
  "files": ["tests/integration/test_custom_xxx.py"],
  "passed": true,
  "total": 0,
  "failed": 0,
  "output": ""
}}
```
"""

    @staticmethod
    def _parse_manifest(output: str) -> dict:
        if not output or not output.strip():
            raise ValueError("Claude returned an empty test manifest.")
        cleaned = output.strip()
        fenced = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            cleaned,
            re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            cleaned = fenced.group(1)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                # Return a safe empty manifest rather than crashing
                return {"stage": "unknown", "tests": [], "files": [], "passed": False, "output": output[-1000:]}
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return {"stage": "unknown", "tests": [], "files": [], "passed": False, "output": output[-1000:]}
        if not isinstance(data, dict):
            raise ValueError("Test manifest must be an object.")
        return data
