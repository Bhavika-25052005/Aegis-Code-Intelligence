import json


class DataModelSerializer:
    def serialize(self, model: dict, fmt: str) -> str:
        if fmt == "json":
            return self.to_json(model)
        elif fmt == "sql":
            return self.to_sql(model)
        elif fmt == "dbml":
            return self.to_dbml(model)
        else:
            raise ValueError(f"Unsupported format: '{fmt}'. Use json, sql, or dbml.")

    def to_json(self, model: dict) -> str:
        return json.dumps(model, indent=2)

    def to_sql(self, model: dict) -> str:
        lines = []
        lines.append("-- Data Model (auto-generated)")
        lines.append(f"-- Version: {model.get('version', 1)}")
        lines.append(f"-- Summary: {model.get('summary', '')}")
        lines.append("")

        for enum in model.get("enums", []):
            name = enum.get("name", "unnamed")
            values = enum.get("values", [])
            val_strs = ", ".join(f"'{v['name']}'" for v in values)
            lines.append(f"CREATE TYPE {name} AS ENUM ({val_strs});")
            lines.append("")

        for entity in model.get("entities", []):
            name = entity.get("name", "unnamed")
            desc = entity.get("description", "")
            if desc:
                lines.append(f"-- {desc}")
            lines.append(f"CREATE TABLE {name} (")

            col_lines = []
            pk_fields = []

            for field in entity.get("fields", []):
                col = self._field_to_sql(field)
                col_lines.append(f"    {col}")
                if field.get("primary_key"):
                    pk_fields.append(field["name"])

            if pk_fields and len(pk_fields) > 1:
                col_lines.append(f"    PRIMARY KEY ({', '.join(pk_fields)})")

            for rel in entity.get("relationships", []):
                if rel.get("type") in ("many_to_one", "one_to_one") and rel.get("foreign_key"):
                    on_delete = rel.get("on_delete", "CASCADE").replace("_", " ")
                    col_lines.append(
                        f"    FOREIGN KEY ({rel['foreign_key']}) "
                        f"REFERENCES {rel['target_entity']}(id) ON DELETE {on_delete}"
                    )

            lines.append(",\n".join(col_lines))
            lines.append(");")
            lines.append("")

            for idx in entity.get("indexes", []):
                unique = "UNIQUE " if idx.get("unique") else ""
                idx_name = idx.get("name", f"idx_{name}_{'_'.join(idx.get('fields', []))}")
                idx_fields = ", ".join(idx.get("fields", []))
                lines.append(f"CREATE {unique}INDEX {idx_name} ON {name} ({idx_fields});")

            if entity.get("indexes"):
                lines.append("")

        return "\n".join(lines)

    def to_dbml(self, model: dict) -> str:
        lines = []
        lines.append(f"// Data Model v{model.get('version', 1)}")
        lines.append(f"// {model.get('summary', '')}")
        lines.append("")

        for entity in model.get("entities", []):
            name = entity.get("name", "unnamed")
            desc = entity.get("description", "")
            lines.append(f"Table {name} {{")
            if desc:
                lines.append(f"  Note: '{desc}'")
            for field in entity.get("fields", []):
                col = self._field_to_dbml(field)
                lines.append(f"  {col}")
            lines.append("}")
            lines.append("")

        refs = []
        for entity in model.get("entities", []):
            for rel in entity.get("relationships", []):
                fk = rel.get("foreign_key", "")
                target = rel.get("target_entity", "")
                if not fk or not target:
                    continue
                rel_type = rel.get("type", "many_to_one")
                char_map = {
                    "many_to_one": ">",
                    "one_to_many": "<",
                    "one_to_one": "-",
                    "many_to_many": "<>",
                }
                char = char_map.get(rel_type, ">")
                refs.append(f"Ref: {entity['name']}.{fk} {char} {target}.id")

        if refs:
            lines.append("")
            for r in refs:
                lines.append(r)
            lines.append("")

        for enum in model.get("enums", []):
            name = enum.get("name", "unnamed")
            lines.append(f"Enum {name} {{")
            for val in enum.get("values", []):
                desc = val.get("description", "")
                if desc:
                    lines.append(f"  {val['name']} [note: '{desc}']")
                else:
                    lines.append(f"  {val['name']}")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _field_to_sql(field: dict) -> str:
        parts = [field.get("name", "unnamed"), field.get("type", "TEXT")]
        if field.get("primary_key"):
            parts.append("PRIMARY KEY")
        if not field.get("nullable", True) and not field.get("primary_key"):
            parts.append("NOT NULL")
        if field.get("unique"):
            parts.append("UNIQUE")
        if field.get("default") is not None:
            parts.append(f"DEFAULT {field['default']}")
        return " ".join(parts)

    @staticmethod
    def _field_to_dbml(field: dict) -> str:
        name = field.get("name", "unnamed")
        ftype = field.get("type", "text").lower()
        constraints = []
        if field.get("primary_key"):
            constraints.append("pk")
        if not field.get("nullable", True):
            constraints.append("not null")
        if field.get("unique"):
            constraints.append("unique")
        if field.get("default") is not None:
            constraints.append(f"default: `{field['default']}`")
        if field.get("description"):
            constraints.append(f"note: '{field['description']}'")

        if constraints:
            return f"{name} {ftype} [{', '.join(constraints)}]"
        return f"{name} {ftype}"
