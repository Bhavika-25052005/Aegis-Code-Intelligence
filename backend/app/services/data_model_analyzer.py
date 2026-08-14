import re


class DataModelAnalyzer:
    def analyze(self, model: dict) -> dict:
        findings = self._run_checks(model)
        return {
            "normalization_level": self._detect_normalization(model),
            "findings": findings,
            "statistics": self._compute_stats(model),
        }

    def _detect_normalization(self, model: dict) -> dict:
        entities = model.get("entities", [])
        violations = {"1nf": [], "2nf": [], "3nf": []}

        for entity in entities:
            fields = entity.get("fields", [])
            for field in fields:
                ftype = field.get("type", "").upper()
                if ftype in ("JSON", "JSONB", "ARRAY"):
                    violations["1nf"].append(
                        f"{entity['name']}.{field['name']} uses {ftype} (non-atomic)"
                    )

            pk_fields = [f for f in fields if f.get("primary_key")]
            if len(pk_fields) > 1:
                non_pk = [f for f in fields if not f.get("primary_key")]
                if non_pk:
                    violations["2nf"].append(
                        f"{entity['name']} has composite PK — check for partial dependencies"
                    )

            non_pk_fields = [f for f in fields if not f.get("primary_key")]
            descriptive_suffixes = ("_name", "_title", "_label", "_description")
            fk_fields = {
                r.get("foreign_key") for r in entity.get("relationships", [])
            }
            for field in non_pk_fields:
                if field["name"] in fk_fields:
                    continue
                for suffix in descriptive_suffixes:
                    if field["name"].endswith(suffix):
                        base = field["name"].replace(suffix, "")
                        if any(f["name"] == f"{base}_id" for f in non_pk_fields):
                            violations["3nf"].append(
                                f"{entity['name']}.{field['name']} may depend on {base}_id (transitive)"
                            )

        if violations["1nf"]:
            level = "Unnormalized"
        elif violations["2nf"]:
            level = "1NF"
        elif violations["3nf"]:
            level = "2NF"
        else:
            level = "3NF+"

        return {
            "detected_level": level,
            "violations": violations,
        }

    def _run_checks(self, model: dict) -> list[dict]:
        findings = []
        entities = model.get("entities", [])
        entity_names = {e.get("name", "").lower() for e in entities}

        for entity in entities:
            name = entity.get("name", "")
            fields = entity.get("fields", [])
            relationships = entity.get("relationships", [])
            field_names = {f.get("name", "") for f in fields}

            # Missing indexes on FK columns
            fk_columns = set()
            for rel in relationships:
                fk = rel.get("foreign_key", "")
                if fk:
                    fk_columns.add(fk)

            for fk in fk_columns:
                fk_field = next((f for f in fields if f["name"] == fk), None)
                if fk_field and not fk_field.get("indexed") and not fk_field.get("primary_key"):
                    findings.append({
                        "severity": "warning",
                        "category": "indexing",
                        "entity": name,
                        "field": fk,
                        "message": f"Foreign key '{fk}' lacks an index",
                        "suggestion": f"Add an index on {name}.{fk} for JOIN performance",
                    })

            # Orphan entities (no relationships)
            if not relationships:
                has_incoming = any(
                    any(
                        r.get("target_entity", "").lower() == name.lower()
                        for r in e.get("relationships", [])
                    )
                    for e in entities
                    if e.get("name") != name
                )
                if not has_incoming:
                    findings.append({
                        "severity": "info",
                        "category": "completeness",
                        "entity": name,
                        "field": None,
                        "message": "Entity has no relationships (orphan)",
                        "suggestion": "Verify this entity doesn't need relationships to other entities",
                    })

            # Missing audit fields
            has_created = "created_at" in field_names
            has_updated = "updated_at" in field_names
            if not has_created or not has_updated:
                missing = []
                if not has_created:
                    missing.append("created_at")
                if not has_updated:
                    missing.append("updated_at")
                findings.append({
                    "severity": "info",
                    "category": "completeness",
                    "entity": name,
                    "field": None,
                    "message": f"Missing audit field(s): {', '.join(missing)}",
                    "suggestion": "Consider adding timestamp fields for auditing",
                })

            # Naming consistency
            snake_count = sum(1 for f in fields if "_" in f.get("name", ""))
            camel_count = sum(
                1 for f in fields
                if re.search(r"[a-z][A-Z]", f.get("name", ""))
            )
            if snake_count > 0 and camel_count > 0:
                findings.append({
                    "severity": "warning",
                    "category": "naming",
                    "entity": name,
                    "field": None,
                    "message": "Mixed naming conventions (snake_case and camelCase)",
                    "suggestion": "Use consistent naming — prefer snake_case for database columns",
                })

            # 1NF violations (JSON/array types)
            for field in fields:
                ftype = field.get("type", "").upper()
                if ftype in ("JSON", "JSONB", "ARRAY"):
                    findings.append({
                        "severity": "warning",
                        "category": "normalization",
                        "entity": name,
                        "field": field["name"],
                        "message": f"Column uses {ftype} type (violates 1NF)",
                        "suggestion": "Consider normalizing into a separate entity if the data has structure",
                    })

            # Relationship target validation
            for rel in relationships:
                target = rel.get("target_entity", "")
                if target and target.lower() not in entity_names:
                    findings.append({
                        "severity": "error",
                        "category": "integrity",
                        "entity": name,
                        "field": rel.get("foreign_key"),
                        "message": f"Relationship references non-existent entity '{target}'",
                        "suggestion": f"Add entity '{target}' or fix the relationship target",
                    })

            # Large entity detection
            if len(fields) > 15:
                findings.append({
                    "severity": "info",
                    "category": "normalization",
                    "entity": name,
                    "field": None,
                    "message": f"Large entity with {len(fields)} fields",
                    "suggestion": "Consider splitting into core and extension entities",
                })

        return findings

    def _compute_stats(self, model: dict) -> dict:
        entities = model.get("entities", [])
        total_fields = sum(len(e.get("fields", [])) for e in entities)
        total_relationships = sum(len(e.get("relationships", [])) for e in entities)
        total_indexes = sum(len(e.get("indexes", [])) for e in entities)

        indexed_fields = sum(
            1 for e in entities
            for f in e.get("fields", [])
            if f.get("indexed") or f.get("primary_key")
        )

        return {
            "entity_count": len(entities),
            "total_fields": total_fields,
            "total_relationships": total_relationships,
            "total_indexes": total_indexes,
            "indexed_field_count": indexed_fields,
            "avg_fields_per_entity": round(total_fields / max(len(entities), 1), 1),
            "enum_count": len(model.get("enums", [])),
        }
