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

    NORMALIZATION_DESCRIPTIONS = {
        "1nf": "First Normal Form (1NF): Eliminate repeating groups, ensure every column contains only atomic values. No arrays, nested objects, or multi-valued columns.",
        "2nf": "Second Normal Form (2NF): Satisfies 1NF plus remove all partial dependencies. Every non-key field must depend on the ENTIRE primary key, not just part of it.",
        "3nf": "Third Normal Form (3NF): Satisfies 2NF plus remove all transitive dependencies. No non-key field should depend on another non-key field.",
        "bcnf": "Boyce-Codd Normal Form (BCNF): Satisfies 3NF plus every determinant must be a candidate key. The strictest practical relational form.",
        "denormalized": "Denormalized (performance-optimized): Intentionally flatten for read performance. Allow duplicate data, pre-computed columns, wide tables, and embedded objects where it improves query speed.",
    }

    OPTIMIZATION_DESCRIPTIONS = {
        "read_heavy": "READ-HEAVY: Add generous indexes on commonly queried fields, consider denormalized read tables or materialized views.",
        "write_heavy": "WRITE-HEAVY: Minimize indexes to avoid write overhead, normalize aggressively, avoid triggers and computed columns.",
        "audit_trail": "AUDIT TRAIL: Add created_at (DATETIME), updated_at (DATETIME), created_by (VARCHAR), updated_by (VARCHAR) to ALL entities.",
        "soft_deletes": "SOFT DELETES: Add deleted_at (nullable DATETIME) to all entities that represent user-facing data. Never physically delete these records.",
        "multi_tenant": "MULTI-TENANT: Add tenant_id (UUID, NOT NULL, indexed) to ALL entities. Include tenant_id in all composite unique constraints and indexes.",
        "versioning": "VERSIONING: Add a version INTEGER column (default 1) to entities for optimistic locking. Increment on every update.",
        "partitioning_ready": "PARTITIONING-READY: Design with partitioning in mind. Include time-based or tenant-based partition keys. Note partition strategy in entity description.",
    }

    async def generate(
        self,
        feature,
        story,
        requirement_analysis: dict,
        implementation_plan: dict,
        existing_data_model: dict | None,
        repository_context: dict,
        user_prompt: str | None = None,
        normalization: str | None = None,
        optimizations: list[str] | None = None,
    ) -> dict:
        prompt = self._build_prompt(
            feature,
            story,
            requirement_analysis,
            implementation_plan,
            existing_data_model,
            repository_context,
            user_prompt,
            normalization,
            optimizations,
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

    async def optimize(
        self,
        existing_model: dict,
        actions: list[str],
    ) -> dict:
        prompt = self._build_optimize_prompt(existing_model, actions)
        result = await self.runner.execute(prompt)

        if not result.success:
            raise DataModelGenerationError(
                result.error or "Data model optimization failed."
            )

        try:
            return self._validate(self._parse_json(result.output))
        except Exception as exc:
            raise DataModelGenerationError(
                f"Claude returned invalid optimized model JSON: {exc}"
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
        normalization: str | None = None,
        optimizations: list[str] | None = None,
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

        if normalization or optimizations:
            constraints_parts = []
            if normalization and normalization in self.NORMALIZATION_DESCRIPTIONS:
                constraints_parts.append(
                    f"Target Normalization: {self.NORMALIZATION_DESCRIPTIONS[normalization]}"
                )
            if optimizations:
                opt_descriptions = [
                    self.OPTIMIZATION_DESCRIPTIONS[o]
                    for o in optimizations
                    if o in self.OPTIMIZATION_DESCRIPTIONS
                ]
                if opt_descriptions:
                    constraints_parts.append(
                        "Optimization Preferences:\n" + "\n".join(f"- {d}" for d in opt_descriptions)
                    )
            if constraints_parts:
                base_context += "\nDESIGN CONSTRAINTS\n" + "\n\n".join(constraints_parts) + "\n"

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

    OPTIMIZE_ACTION_PROMPTS = {
        "normalize_3nf": "NORMALIZE TO 3NF: Identify and eliminate transitive dependencies. Split entities where a non-key field depends on another non-key field. Create junction tables for any remaining multi-valued attributes.",
        "add_indexes": "ADD MISSING INDEXES: Add indexes to all foreign key columns, frequently filtered columns, and columns likely used in WHERE/JOIN clauses. Add composite indexes where queries would benefit.",
        "add_audit_fields": "ADD AUDIT FIELDS: Add created_at (DATETIME, default NOW), updated_at (DATETIME), created_by (VARCHAR), updated_by (VARCHAR) to ALL entities that don't already have them.",
        "add_soft_deletes": "ADD SOFT DELETES: Add deleted_at (DATETIME, nullable, indexed) to all entities representing user data. Do not add to junction/mapping tables.",
        "split_large_entities": "SPLIT LARGE ENTITIES: Any entity with more than 15 fields should be split into a core entity and extension entities linked by 1:1 relationships. Group related fields together.",
        "remove_redundant_fields": "REMOVE REDUNDANT FIELDS: Remove fields that store data already derivable from relationships (e.g., a 'total_orders' field on a user when orders can be counted). Record removals in change_log.",
    }

    def _build_optimize_prompt(self, existing_model: dict, actions: list[str]) -> str:
        version = existing_model.get("version", 1)
        action_instructions = []
        for action in actions:
            if action in self.OPTIMIZE_ACTION_PROMPTS:
                action_instructions.append(self.OPTIMIZE_ACTION_PROMPTS[action])

        if not action_instructions:
            action_instructions.append("Apply general best practices: add missing indexes, fix naming inconsistencies, ensure referential integrity.")

        return f"""# Data Model Optimization

You are a senior database architect optimizing an existing data model.
Apply the requested optimizations while preserving the model's purpose and relationships.

You may use Read, Glob and Grep to inspect the repository. Do NOT create or modify any files.

EXISTING DATA MODEL (version {version}):
{json.dumps(existing_model, indent=2)}

OPTIMIZATIONS TO APPLY:
{chr(10).join(f"{i+1}. {inst}" for i, inst in enumerate(action_instructions))}

RULES:
1. Apply ALL requested optimizations systematically.
2. Record EVERY change in the change_log array (entity name, action, reason, fields_changed).
3. Return the COMPLETE updated model (not just changes).
4. Increment version to {version + 1}.
5. Keep project_mode as "existing_project".
6. Update the summary to reflect optimizations applied.
7. Preserve entity relationships and referential integrity.
8. Return ONLY valid JSON. No prose before or after.

Return exactly this structure:
{{
  "version": {version + 1},
  "project_mode": "existing_project",
  "summary": "Updated summary reflecting optimizations",
  "entities": [...],
  "enums": [...],
  "change_log": [
    {{
      "entity": "EntityName",
      "action": "created | modified | removed",
      "reason": "What optimization was applied",
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
