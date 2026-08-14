import json
import logging
import re

from app.services.claude_runner import ClaudeRunner

logger = logging.getLogger(__name__)


class DataModelGenerationError(Exception):
    pass


class DataModelGenerator:
    def __init__(
        self,
        workspace_path: str,
        max_budget_usd: float = 1.0,
    ):
        self.runner = ClaudeRunner(
            workspace_path=workspace_path,
            max_budget_usd=max_budget_usd,
            allowed_tools="Read,Glob,Grep",
        )

    async def generate(
        self,
        feature,
        story,
        requirement_analysis: dict,
        implementation_plan: dict,
        existing_data_model: dict | None,
        repository_context: dict,
        user_prompt: str | None = None,
    ) -> dict:
        prompt = self._build_prompt(
            feature,
            story,
            requirement_analysis,
            implementation_plan,
            existing_data_model,
            repository_context,
            user_prompt,
        )
        result = await self.runner.execute(prompt)

        if not result.success:
            raise DataModelGenerationError(
                result.error or "Data model generation failed."
            )

        try:
            return self._validate(self._parse_json(result.output))
        except Exception as exc:
            raise DataModelGenerationError(
                f"Claude returned invalid data model JSON: {exc}"
            ) from exc

    def _build_prompt(
        self,
        feature,
        story,
        requirement_analysis: dict,
        implementation_plan: dict,
        existing_data_model: dict | None,
        repository_context: dict,
        user_prompt: str | None = None,
    ) -> str:
        is_enhancement = existing_data_model is not None

        tasks = [
            {"title": task.title, "description": task.description or ""}
            for task in story.tasks
        ]

        ac_items = requirement_analysis.get("acceptance_criteria", [])
        fr_items = requirement_analysis.get("functional_rules", [])
        ec_items = requirement_analysis.get("edge_cases", [])

        planned_changes = implementation_plan.get("planned_changes", [])
        work_summary = implementation_plan.get("work_summary", "")
        architecture_notes = implementation_plan.get("architecture_notes", [])

        base_context = f"""
FEATURE
Title: {feature.title}
Description: {feature.description or "Not provided"}

USER STORY
Title: {story.title}
Description: {story.description or "Not provided"}

TASKS
{json.dumps(tasks, indent=2)}

APPROVED REQUIREMENT CONTRACT
Acceptance Criteria:
{json.dumps(ac_items, indent=2)}

Functional Rules:
{json.dumps(fr_items, indent=2)}

Edge Cases:
{json.dumps(ec_items, indent=2)}

APPROVED IMPLEMENTATION PLAN
Work Summary: {work_summary}
Architecture Notes: {json.dumps(architecture_notes, indent=2)}
Planned Changes: {json.dumps(planned_changes, indent=2)}

REPOSITORY CONTEXT
{json.dumps(repository_context, indent=2)}
"""

        if user_prompt:
            base_context += f"""
USER INSTRUCTIONS
The user provided the following additional guidance for data model generation.
You MUST incorporate these instructions into your data model design:
{user_prompt}
"""

        if is_enhancement:
            return self._enhancement_prompt(base_context, existing_data_model)
        return self._new_project_prompt(base_context)

    @staticmethod
    def _new_project_prompt(base_context: str) -> str:
        return f"""# Data Model Generation — New Project

You are a senior database architect designing a data model from scratch.
Based on the implementation plan and requirement analysis below,
design a complete, detailed data model.

You may use Read, Glob and Grep to inspect the repository for existing models,
schemas, or ORM definitions. Do NOT create or modify any files.

{base_context}

RULES:
1. Define every entity (table/model) the feature requires.
2. Include ALL fields with: name, type, primary_key, nullable, unique, indexed, default, description.
3. Use standard SQL/ORM types: UUID, VARCHAR(N), INTEGER, BIGINT, FLOAT, DECIMAL(P,S), BOOLEAN, TEXT, DATETIME, DATE, JSON.
4. Define relationships between entities with: type, target_entity, foreign_key, on_delete, description.
5. Include composite indexes and unique constraints where performance or data integrity demands.
6. Add audit fields (created_at, updated_at) where appropriate.
7. Define enums separately from entities with name, description, and values with descriptions.
8. Consider soft deletes, versioning, and audit trails only if the requirement implies them.
9. Do NOT invent entities or fields unrelated to the requirement.
10. Make every field description clear and useful for a developer.
11. Return ONLY valid JSON. No prose before or after.

Return exactly this structure:
{{
  "version": 1,
  "project_mode": "new_project",
  "summary": "Brief overview of what the data model represents",
  "entities": [
    {{
      "name": "EntityName",
      "description": "What this entity represents and why it exists",
      "type": "table",
      "fields": [
        {{
          "name": "field_name",
          "type": "VARCHAR(255)",
          "primary_key": false,
          "nullable": false,
          "unique": false,
          "indexed": false,
          "default": null,
          "description": "Clear explanation of this field's purpose"
        }}
      ],
      "relationships": [
        {{
          "type": "one_to_many | many_to_one | many_to_many | one_to_one",
          "target_entity": "OtherEntity",
          "foreign_key": "other_entity_id",
          "on_delete": "CASCADE | SET_NULL | RESTRICT",
          "description": "Explanation of this relationship"
        }}
      ],
      "indexes": [
        {{
          "name": "idx_entity_field",
          "fields": ["field1", "field2"],
          "unique": false
        }}
      ],
      "constraints": ["Business constraint description"]
    }}
  ],
  "enums": [
    {{
      "name": "EnumName",
      "description": "What this enum represents",
      "values": [
        {{ "name": "VALUE", "description": "What this value means" }}
      ]
    }}
  ],
  "change_log": []
}}
""".strip()

    @staticmethod
    def _enhancement_prompt(base_context: str, existing_model: dict) -> str:
        version = existing_model.get("version", 1)
        return f"""# Data Model Update — Enhancement

You are a senior database architect updating an existing data model.
Based on the new requirement and implementation plan, update the model incrementally.

You may use Read, Glob and Grep to inspect the repository. Do NOT create or modify any files.

EXISTING DATA MODEL (version {version}):
{json.dumps(existing_model, indent=2)}

{base_context}

RULES:
1. PRESERVE all existing entities and fields unless the requirement explicitly replaces them.
2. ADD new entities and fields as needed by the new requirement.
3. MODIFY existing entities only if the requirement demands changes to them.
4. Record EVERY change in the change_log array (entity name, action, reason, fields_changed).
5. If no changes are needed to an existing entity, include it unchanged.
6. New relationships must correctly reference existing or new entities.
7. Return the COMPLETE updated model (not just the diff).
8. Increment the version number to {version + 1}.
9. Keep project_mode as "existing_project".
10. Do NOT remove entities or fields unless the requirement explicitly says to.
11. Return ONLY valid JSON. No prose before or after.

Return exactly the same structure as the existing model with updates applied:
{{
  "version": {version + 1},
  "project_mode": "existing_project",
  "summary": "Updated summary reflecting new additions",
  "entities": [...],
  "enums": [...],
  "change_log": [
    {{
      "entity": "EntityName",
      "action": "created | modified | removed",
      "reason": "Why this change was made",
      "fields_changed": ["field1", "field2"]
    }}
  ]
}}
""".strip()

    @staticmethod
    def _parse_json(output: str) -> dict:
        if not output or not output.strip():
            raise ValueError("Claude returned an empty response.")

        cleaned = output.strip()

        try:
            envelope = json.loads(cleaned)
            if isinstance(envelope, dict) and "result" in envelope:
                inner = envelope["result"]
                if isinstance(inner, str) and inner.strip():
                    cleaned = inner.strip()
                elif isinstance(inner, dict):
                    return inner
        except json.JSONDecodeError:
            pass

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
                raise ValueError("No JSON object found in data model output.")
            data = json.loads(cleaned[start : end + 1])

        if not isinstance(data, dict):
            raise ValueError("Data model must be a JSON object.")

        return data

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
