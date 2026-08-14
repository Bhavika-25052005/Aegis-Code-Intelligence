import json


class DataModelSerializer:
    def serialize(self, model: dict, fmt: str) -> str:
        if fmt == "json":
            return json.dumps(model, indent=2)
        elif fmt == "sql":
            return self.to_sql(model)
        elif fmt == "dbml":
            return self.to_dbml(model)
        raise ValueError(f"Unsupported format: '{fmt}'. Use json, sql, or dbml.")

    def to_sql(self, model: dict) -> str:
        lines = ["-- Data Model (auto-generated)", f"-- Version: {model.get('version', 1)}", f"-- {model.get('summary', '')}", ""]
        for enum in model.get("enums", []):
            vals = ", ".join(f"'{v['name']}'" for v in enum.get("values", []))
            lines += [f"CREATE TYPE {enum['name']} AS ENUM ({vals});", ""]
        for entity in model.get("entities", []):
            name = entity.get("name", "unnamed")
            if entity.get("description"):
                lines.append(f"-- {entity['description']}")
            lines.append(f"CREATE TABLE {name} (")
            col_lines = []
            for field in entity.get("fields", []):
                parts = [field["name"], field.get("type", "TEXT")]
                if field.get("primary_key"):
                    parts.append("PRIMARY KEY")
                if not field.get("nullable", True) and not field.get("primary_key"):
                    parts.append("NOT NULL")
                if field.get("unique"):
                    parts.append("UNIQUE")
                if field.get("default") is not None:
                    parts.append(f"DEFAULT {field['default']}")
                col_lines.append(f"    {' '.join(parts)}")
            for rel in entity.get("relationships", []):
                if rel.get("type") in ("many_to_one", "one_to_one") and rel.get("foreign_key"):
                    od = rel.get("on_delete", "CASCADE").replace("_", " ")
                    col_lines.append(f"    FOREIGN KEY ({rel['foreign_key']}) REFERENCES {rel['target_entity']}(id) ON DELETE {od}")
            lines.append(",\n".join(col_lines))
            lines += [");", ""]
            for idx in entity.get("indexes", []):
                u = "UNIQUE " if idx.get("unique") else ""
                lines.append(f"CREATE {u}INDEX {idx['name']} ON {name} ({', '.join(idx.get('fields', []))});")
            if entity.get("indexes"):
                lines.append("")
        return "\n".join(lines)

    def to_dbml(self, model: dict) -> str:
        lines = [f"// Data Model v{model.get('version', 1)}", f"// {model.get('summary', '')}", ""]
        for entity in model.get("entities", []):
            lines.append(f"Table {entity.get('name', 'unnamed')} {{")
            if entity.get("description"):
                lines.append(f"  Note: '{entity['description']}'")
            for field in entity.get("fields", []):
                c = []
                if field.get("primary_key"):
                    c.append("pk")
                if not field.get("nullable", True):
                    c.append("not null")
                if field.get("unique"):
                    c.append("unique")
                if field.get("default") is not None:
                    c.append(f"default: `{field['default']}`")
                if field.get("description"):
                    c.append(f"note: '{field['description']}'")
                suffix = f" [{', '.join(c)}]" if c else ""
                lines.append(f"  {field['name']} {field.get('type','text').lower()}{suffix}")
            lines += ["}", ""]
        refs = []
        char_map = {"many_to_one": ">", "one_to_many": "<", "one_to_one": "-", "many_to_many": "<>"}
        for entity in model.get("entities", []):
            for rel in entity.get("relationships", []):
                if rel.get("foreign_key") and rel.get("target_entity"):
                    refs.append(f"Ref: {entity['name']}.{rel['foreign_key']} {char_map.get(rel['type'], '>')} {rel['target_entity']}.id")
        if refs:
            lines += refs + [""]
        for enum in model.get("enums", []):
            lines.append(f"Enum {enum['name']} {{")
            for v in enum.get("values", []):
                if v.get("description"):
                    lines.append(f"  {v['name']} [note: '{v['description']}']")
                else:
                    lines.append(f"  {v['name']}")
            lines += ["}", ""]
        return "\n".join(lines)
