import json
import re

from app.services.claude_runner import ClaudeRunner


class ImplementationPlanningError(Exception):
    pass


class ImplementationPlanner:
    """
    Read-only implementation planning.
    The planner may inspect repository files but cannot edit them.
    It must order ONLY existing imported tasks; it cannot invent
    new executable tasks.
    """

    def __init__(
        self,
        workspace_path: str,
        max_budget_usd: float = 1.5,
    ):
        self.runner = ClaudeRunner(
            workspace_path=workspace_path,
            max_budget_usd=max_budget_usd,
            allowed_tools="Read,Glob,Grep",
        )

    async def create_plan(
        self,
        feature,
        story,
        requirement_analysis: dict,
        repository_context: dict,
    ) -> dict:
        prompt = self._build_prompt(
            feature,
            story,
            requirement_analysis,
            repository_context,
        )
        result = await self.runner.execute(prompt)

        if not result.success:
            raise ImplementationPlanningError(
                result.error or "Implementation planning failed."
            )

        try:
            plan = self._parse_json(result.output)
            return self._validate_plan(plan, story)
        except Exception as exc:
            raise ImplementationPlanningError(
                f"Claude returned invalid implementation-plan JSON: {exc}"
            ) from exc

    @staticmethod
    def _build_prompt(
        feature,
        story,
        requirement_analysis: dict,
        repository_context: dict,
    ) -> str:
        tasks = [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description or "",
                "imported_order": task.order,
            }
            for task in story.tasks
        ]

        return f"""
# Aegis Implementation Intelligence

You are a senior software architect.
The requirement below has already been analysed and approved by a human.
Your job is NOT to write code. Create a repository-aware implementation
plan and a dependency-safe execution order for the EXISTING imported tasks.

You may use Read, Glob and Grep.
Do NOT edit or create source files.

FEATURE
{feature.title}
{feature.description or "No description provided"}

USER STORY
{story.title}
{story.description or "No description provided"}

APPROVED REQUIREMENT CONTRACT
{json.dumps(requirement_analysis, indent=2)}

IMPORTED TASKS
{json.dumps(tasks, indent=2)}

REPOSITORY INTELLIGENCE
{json.dumps(repository_context, indent=2)}

RULES
1. Use every imported task exactly once.
2. Do NOT create extra executable tasks.
3. execution_order must be unique and sequential.
4. depends_on may contain only imported task IDs.
5. A task cannot depend on itself.
6. Dependencies must be acyclic.
7. Reuse/modify existing code where possible.
8. If repository_empty=true, plan from scratch using visible conventions.
9. Keep changes minimal and map them to approved acceptance criteria.
10. Include test strategy only as Test Intelligence handoff; do not replace Aegis testing here.
11. No parallel-execution fields are required.
12. Return ONLY valid JSON.

Return exactly:
{{
  "project_mode": "new_project | existing_project",
  "work_summary": "short approach",
  "architecture_notes": ["observation"],
  "relevant_files": [
    {{
      "path": "relative/path",
      "action": "inspect | reuse | modify",
      "reason": "why it matters"
    }}
  ],
  "planned_changes": [
    {{
      "path": "relative/path",
      "action": "create | modify | reuse",
      "purpose": "one-line purpose",
      "reason": "why this file is needed for this task",
      "acceptance_criteria": ["criterion"]
    }}
  ],
  "task_plan": [
    {{
      "task_id": "existing task id",
      "task_title": "existing task title",
      "execution_order": 1,
      "depends_on": [],
      "approach": "implementation approach",
      "related_files": ["relative/path"]
    }}
  ],
  "test_strategy": [
    {{
      "type": "unit | integration | boundary | negative",
      "target": "what Test Intelligence should verify",
      "cases": ["case"]
    }}
  ],
  "risks": ["risk"],
  "dependencies": ["technical dependency"],
  "out_of_scope": ["explicitly excluded work"]
}}
""".strip()

    @staticmethod
    def _parse_json(output: str) -> dict:
        if not output or not output.strip():
            raise ValueError("Claude returned an empty response.")

        cleaned = output.strip()
        fenced = re.search(
            r"```(?:json)?\s*(\{.*\})\s*```",
            cleaned,
            re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            cleaned = fenced.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found.")
            data = json.loads(cleaned[start:end + 1])

        # Defensive compatibility with Claude CLI envelope.
        if (
            isinstance(data, dict)
            and "result" in data
            and "work_summary" not in data
        ):
            inner = data.get("result")
            if isinstance(inner, str):
                data = json.loads(inner.strip())
            elif isinstance(inner, dict):
                data = inner

        if not isinstance(data, dict):
            raise ValueError("Implementation plan must be an object.")

        for field in [
            "architecture_notes", "relevant_files", "planned_changes",
            "task_plan", "test_strategy", "risks", "dependencies",
            "out_of_scope",
        ]:
            if not isinstance(data.get(field), list):
                data[field] = []

        data["work_summary"] = str(data.get("work_summary", "")).strip()
        if not data["work_summary"]:
            raise ValueError("work_summary is required.")

        return data

    @staticmethod
    def _validate_plan(plan: dict, story) -> dict:
        imported = {task.id: task for task in story.tasks}
        raw_plan = plan.get("task_plan", [])
        plan_ids = [str(item.get("task_id", "")) for item in raw_plan]

        if set(plan_ids) != set(imported.keys()):
            raise ValueError(
                "task_plan must contain every imported task exactly once "
                "and no extra tasks."
            )

        if len(plan_ids) != len(set(plan_ids)):
            raise ValueError("Duplicate task IDs in task_plan.")

        normalized = []
        for item in raw_plan:
            task_id = item["task_id"]
            depends_on = [
                dep
                for dep in item.get("depends_on", [])
                if dep in imported and dep != task_id
            ]
            normalized.append(
                {
                    **item,
                    "task_id": task_id,
                    "task_title": imported[task_id].title,
                    "execution_order": int(
                        item.get("execution_order", 999999)
                    ),
                    "depends_on": list(dict.fromkeys(depends_on)),
                }
            )

        normalized.sort(key=lambda item: item["execution_order"])
        for index, item in enumerate(normalized, start=1):
            item["execution_order"] = index

        graph = {
            item["task_id"]: item["depends_on"]
            for item in normalized
        }

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str):
            if task_id in visited:
                return
            if task_id in visiting:
                raise ValueError("Cyclic task dependency detected.")
            visiting.add(task_id)
            for dependency in graph.get(task_id, []):
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)

        plan["task_plan"] = normalized

        mode = str(plan.get("project_mode", "existing_project")).lower()
        if mode not in {"new_project", "existing_project"}:
            mode = "existing_project"
        plan["project_mode"] = mode

        return plan
