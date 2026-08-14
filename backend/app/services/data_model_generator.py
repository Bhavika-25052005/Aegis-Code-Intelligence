import json
import logging
import re

from app.services.claude_runner import ClaudeRunner

logger = logging.getLogger(__name__)


class DataModelGenerationError(Exception):
    pass


class DataModelGenerator:
    def __init__(self, workspace_path: str, max_budget_usd: float = 1.5):
        self.runner = ClaudeRunner(
            workspace_path=workspace_path,
            max_budget_usd=max_budget_usd,
            allowed_tools="Read,Glob,Grep",
        )

    async def generate(self, feature, story, requirement_analysis: dict, implementation_plan: dict, existing_data_model: dict | None, repository_context: dict, user_prompt: str | None = None) -> dict:
        prompt = self._build_prompt(feature, story, requirement_analysis, implementation_plan, existing_data_model, repository_context, user_prompt)
        result = await self.runner.execute(prompt)
        if not result.success:
            raise DataModelGenerationError(result.error or "Data model generation failed.")
        try:
            return self._validate(self._parse_json(result.output))
        except Exception as exc:
            raise DataModelGenerationError(f"Claude returned invalid data model JSON: {exc}") from exc

    def _build_prompt(self, feature, story, requirement_analysis, implementation_plan, existing_data_model, repository_context, user_prompt=None):
        is_enhancement = existing_data_model is not None
        tasks = [{"title": task.title, "description": task.description or ""} for task in story.tasks]
        ac_items = requirement_analysis.get("acceptance_criteria", [])
        fr_items = requirement_analysis.get("functional_rules", [])
        planned_changes = implementation_plan.get("planned_changes", [])
        work_summary = implementation_plan.get("work_summary", "")
        architecture_notes = implementation_plan.get("architecture_notes", [])

        base_context = f"""
FEATURE: {feature.title}
USER STORY: {story.title}
TASKS: {json.dumps(tasks, indent=2)}
ACCEPTANCE CRITERIA: {json.dumps(ac_items, indent=2)}
FUNCTIONAL RULES: {json.dumps(fr_items, indent=2)}
IMPLEMENTATION PLAN SUMMARY: {work_summary}
ARCHITECTURE NOTES: {json.dumps(architecture_notes, indent=2)}
PLANNED CHANGES: {json.dumps(planned_changes, indent=2)}
REPOSITORY CONTEXT: {json.dumps(repository_context, indent=2)}
"""
        if user_prompt:
            base_context += f"\nUSER INSTRUCTIONS: {user_prompt}\n"

        if is_enhancement:
            return self._enhancement_prompt(base_context, existing_data_model)
        return self._new_project_prompt(base_context)

    @staticmethod
    def _new_project_prompt(base_context: str) -> str:
        return f"""You are a senior database architect. Design a complete data model based on the implementation plan below.
You may use Read, Glob, Grep to inspect the repository. Do NOT modify any files.

{base_context}

RULES:
1. Define every entity the feature requires with all fields.
2. Use types: UUID, VARCHAR(N), INTEGER, BIGINT, FLOAT, DECIMAL(P,S), BOOLEAN, TEXT, DATETIME, DATE, JSON.
3. Define relationships with type, target_entity, foreign_key, on_delete, description.
4. Include indexes and constraints where needed.
5. Add audit fields (created_at, updated_at) where appropriate.
6. Define enums separately.
7. Do NOT invent entities unrelated to the requirement.
8. Return ONLY valid JSON, no prose.

Return exactly:
{{
  "version": 1,
  "project_mode": "new_project",
  "summary": "Brief overview",
  "entities": [
    {{
      "name": "EntityName",
      "description": "What this entity represents",
      "type": "table",
      "fields": [
        {{"name": "id", "type": "UUID", "primary_key": true, "nullable": false, "unique": true, "indexed": true, "default": null, "description": "Primary key"}}
      ],
      "relationships": [
        {{"type": "many_to_one", "target_entity": "OtherEntity", "foreign_key": "other_id", "on_delete": "CASCADE", "description": "Relationship description"}}
      ],
      "indexes": [
        {{"name": "idx_entity_field", "fields": ["field1"], "unique": false}}
      ],
      "constraints": []
    }}
  ],
  "enums": [
    {{"name": "EnumName", "description": "What this enum is", "values": [{{"name": "VALUE", "description": "meaning"}}]}}
  ],
  "change_log": []
}}""".strip()

    @staticmethod
    def _enhancement_prompt(base_context: str, existing_model: dict) -> str:
        version = existing_model.get("version", 1)
        return f"""You are a senior database architect updating an existing data model.
You may use Read, Glob, Grep to inspect the repository. Do NOT modify any files.

EXISTING DATA MODEL (version {version}):
{json.dumps(existing_model, indent=2)}

{base_context}

RULES:
1. PRESERVE all existing entities and fields unless the requirement explicitly replaces them.
2. ADD new entities/fields as needed. MODIFY existing only if required.
3. Record every change in change_log.
4. Return the COMPLETE updated model. Increment version to {version + 1}.
5. Return ONLY valid JSON.

Return same structure with updates applied and version = {version + 1}.""".strip()

    @staticmethod
    def _parse_json(output: str) -> dict:
        if not output or not output.strip():
            raise ValueError("Empty response.")
        cleaned = output.strip()
        try:
            envelope = json.loads(cleaned)
            if isinstance(envelope, dict) and "result" in envelope:
                inner = envelope["result"]
                if isinstance(inner, str):
                    cleaned = inner.strip()
                elif isinstance(inner, dict):
                    return inner
        except json.JSONDecodeError:
            pass
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start == -1 or end <= start:
                raise ValueError("No JSON object found.")
            return json.loads(cleaned[start:end + 1])

    @staticmethod
    def _validate(data: dict) -> dict:
        if not isinstance(data.get("entities"), list):
            data["entities"] = []
        if not isinstance(data.get("enums"), list):
            data["enums"] = []
        if not isinstance(data.get("change_log"), list):
            data["change_log"] = []
        data.setdefault("version", 1)
        data.setdefault("project_mode", "new_project")
        data.setdefault("summary", "")
        for entity in data["entities"]:
            if not isinstance(entity, dict):
                continue
            entity.setdefault("name", "Unnamed")
            entity.setdefault("description", "")
            entity.setdefault("type", "table")
            if not isinstance(entity.get("fields"), list):
                entity["fields"] = []
            if not isinstance(entity.get("relationships"), list):
                entity["relationships"] = []
            if not isinstance(entity.get("indexes"), list):
                entity["indexes"] = []
            if not isinstance(entity.get("constraints"), list):
                entity["constraints"] = []
            for field in entity["fields"]:
                if not isinstance(field, dict):
                    continue
                field.setdefault("name", "unnamed")
                field.setdefault("type", "VARCHAR(255)")
                field.setdefault("primary_key", False)
                field.setdefault("nullable", True)
                field.setdefault("unique", False)
                field.setdefault("indexed", False)
                field.setdefault("default", None)
                field.setdefault("description", "")
            for rel in entity["relationships"]:
                if not isinstance(rel, dict):
                    continue
                rel.setdefault("type", "one_to_many")
                rel.setdefault("target_entity", "")
                rel.setdefault("foreign_key", "")
                rel.setdefault("on_delete", "CASCADE")
                rel.setdefault("description", "")
        for enum in data["enums"]:
            if not isinstance(enum, dict):
                continue
            enum.setdefault("name", "Unnamed")
            enum.setdefault("description", "")
            if not isinstance(enum.get("values"), list):
                enum["values"] = []
        return data
