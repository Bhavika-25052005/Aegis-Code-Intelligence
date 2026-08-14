import json
import logging
import re
from pathlib import Path

from app.services.data_model_generator import DataModelGenerator

logger = logging.getLogger(__name__)


class DataModelParseError(Exception):
    pass


class DataModelParser:
    def parse(self, content: bytes, filename: str) -> dict:
        ext = Path(filename).suffix.lower()
        if ext == ".json":
            return self._parse_json(content)
        elif ext == ".sql":
            return self._parse_sql(content)
        elif ext == ".dbml":
            return self._parse_dbml(content)
        else:
            raise DataModelParseError(
                f"Unsupported format: '{ext}'. Supported formats: .json, .sql, .dbml"
            )

    def _parse_json(self, content: bytes) -> dict:
        try:
            data = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise DataModelParseError(f"Invalid JSON file: {e}") from e

        if not isinstance(data, dict):
            raise DataModelParseError("JSON root must be an object.")

        return DataModelGenerator._validate(data)

    def _parse_sql(self, content: bytes) -> dict:
        try:
            sql = content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise DataModelParseError(f"Cannot decode file: {e}") from e

        sql = re.sub(r"--[^\n]*", "", sql)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)

        entities = []
        enums = []

        create_type_pattern = re.compile(
            r"CREATE\s+TYPE\s+(\w+)\s+AS\s+ENUM\s*\(([^)]+)\)",
            re.IGNORECASE | re.DOTALL,
        )
        for m in create_type_pattern.finditer(sql):
            enum_name = m.group(1)
            values_raw = m.group(2)
            values = []
            for val in re.findall(r"'([^']+)'", values_raw):
                values.append({"name": val, "description": ""})
            enums.append({"name": enum_name, "description": "", "values": values})

        table_pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\((.+?)\)\s*;",
            re.IGNORECASE | re.DOTALL,
        )

        for match in table_pattern.finditer(sql):
            table_name = match.group(1)
            body = match.group(2)

            fields = []
            relationships = []
            indexes = []
            constraints = []

            lines = self._split_columns(body)

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if re.match(r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY", line, re.IGNORECASE):
                    fk_match = re.search(
                        r"FOREIGN\s+KEY\s*\((\w+)\)\s*REFERENCES\s+(\w+)\s*\((\w+)\)(?:\s+ON\s+DELETE\s+(\w+(?:\s+\w+)?))?",
                        line, re.IGNORECASE,
                    )
                    if fk_match:
                        relationships.append({
                            "type": "many_to_one",
                            "target_entity": fk_match.group(2),
                            "foreign_key": fk_match.group(1),
                            "on_delete": (fk_match.group(4) or "CASCADE").upper().replace(" ", "_"),
                            "description": "",
                        })
                    continue

                if re.match(r"(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY", line, re.IGNORECASE):
                    continue

                if re.match(r"(?:CONSTRAINT\s+\w+\s+)?UNIQUE", line, re.IGNORECASE):
                    unique_match = re.search(r"UNIQUE\s*\(([^)]+)\)", line, re.IGNORECASE)
                    if unique_match:
                        idx_fields = [f.strip().strip("`\"[]") for f in unique_match.group(1).split(",")]
                        indexes.append({
                            "name": f"uq_{table_name}_{'_'.join(idx_fields)}",
                            "fields": idx_fields,
                            "unique": True,
                        })
                    continue

                if re.match(r"(?:CONSTRAINT|CHECK|INDEX)", line, re.IGNORECASE):
                    constraints.append(line)
                    continue

                field = self._parse_sql_column(line)
                if field:
                    if "REFERENCES" in line.upper():
                        ref_match = re.search(
                            r"REFERENCES\s+(\w+)\s*\((\w+)\)(?:\s+ON\s+DELETE\s+(\w+(?:\s+\w+)?))?",
                            line, re.IGNORECASE,
                        )
                        if ref_match:
                            relationships.append({
                                "type": "many_to_one",
                                "target_entity": ref_match.group(1),
                                "foreign_key": field["name"],
                                "on_delete": (ref_match.group(3) or "CASCADE").upper().replace(" ", "_"),
                                "description": "",
                            })
                    fields.append(field)

            entities.append({
                "name": table_name,
                "description": "",
                "type": "table",
                "fields": fields,
                "relationships": relationships,
                "indexes": indexes,
                "constraints": constraints,
            })

        idx_pattern = re.compile(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)",
            re.IGNORECASE,
        )
        for m in idx_pattern.finditer(sql):
            idx_name = m.group(1)
            tbl_name = m.group(2)
            idx_fields = [f.strip().strip("`\"[]") for f in m.group(3).split(",")]
            is_unique = "UNIQUE" in m.group(0).upper().split("INDEX")[0]
            for entity in entities:
                if entity["name"].lower() == tbl_name.lower():
                    entity["indexes"].append({
                        "name": idx_name,
                        "fields": idx_fields,
                        "unique": is_unique,
                    })
                    break

        if not entities:
            raise DataModelParseError("No CREATE TABLE statements found in the SQL file.")

        model = {
            "version": 1,
            "project_mode": "new_project",
            "summary": f"Uploaded SQL schema with {len(entities)} table(s)",
            "entities": entities,
            "enums": enums,
            "change_log": [],
        }
        return DataModelGenerator._validate(model)

    def _parse_dbml(self, content: bytes) -> dict:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise DataModelParseError(f"Cannot decode file: {e}") from e

        entities = []
        enums = []
        standalone_refs = []

        enum_pattern = re.compile(
            r"[Ee]num\s+(\w+)\s*\{([^}]*)\}", re.DOTALL
        )
        for m in enum_pattern.finditer(text):
            enum_name = m.group(1)
            body = m.group(2)
            values = []
            for line in body.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("[")
                val_name = parts[0].strip().strip("'\"")
                desc = ""
                if len(parts) > 1:
                    note_match = re.search(r"note:\s*['\"]([^'\"]+)['\"]", parts[1], re.IGNORECASE)
                    if note_match:
                        desc = note_match.group(1)
                if val_name:
                    values.append({"name": val_name, "description": desc})
            enums.append({"name": enum_name, "description": "", "values": values})

        table_pattern = re.compile(
            r"[Tt]able\s+(\w+)(?:\s+as\s+\w+)?\s*\{([^}]*)\}", re.DOTALL
        )
        for m in table_pattern.finditer(text):
            table_name = m.group(1)
            body = m.group(2)
            fields = []
            relationships = []
            indexes = []

            for line in body.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("//") or line.startswith("Note:"):
                    continue

                if line.lower().startswith("indexes"):
                    continue

                col_match = re.match(r"(\w+)\s+(\S+)(?:\s+\[([^\]]*)\])?", line)
                if not col_match:
                    continue

                col_name = col_match.group(1)
                col_type = col_match.group(2)
                constraints_str = col_match.group(3) or ""

                is_pk = bool(re.search(r"\bpk\b", constraints_str, re.IGNORECASE))
                is_not_null = bool(re.search(r"\bnot\s+null\b", constraints_str, re.IGNORECASE))
                is_unique = bool(re.search(r"\bunique\b", constraints_str, re.IGNORECASE))
                is_increment = bool(re.search(r"\bincrement\b", constraints_str, re.IGNORECASE))

                default_match = re.search(r"default:\s*[`'\"]?([^`'\",\]]+)[`'\"]?", constraints_str, re.IGNORECASE)
                default_val = default_match.group(1).strip() if default_match else None

                note_match = re.search(r"note:\s*['\"]([^'\"]+)['\"]", constraints_str, re.IGNORECASE)
                description = note_match.group(1) if note_match else ""

                ref_match = re.search(r"ref:\s*([<>\-])\s*(\w+)\.(\w+)", constraints_str, re.IGNORECASE)
                if ref_match:
                    ref_type_char = ref_match.group(1)
                    ref_table = ref_match.group(2)
                    rel_type_map = {">": "many_to_one", "<": "one_to_many", "-": "one_to_one"}
                    relationships.append({
                        "type": rel_type_map.get(ref_type_char, "many_to_one"),
                        "target_entity": ref_table,
                        "foreign_key": col_name,
                        "on_delete": "CASCADE",
                        "description": "",
                    })

                mapped_type = self._map_dbml_type(col_type)

                fields.append({
                    "name": col_name,
                    "type": mapped_type,
                    "primary_key": is_pk,
                    "nullable": not is_pk and not is_not_null,
                    "unique": is_unique,
                    "indexed": is_pk,
                    "default": default_val,
                    "description": description,
                })

            entities.append({
                "name": table_name,
                "description": "",
                "type": "table",
                "fields": fields,
                "relationships": relationships,
                "indexes": indexes,
                "constraints": [],
            })

        ref_pattern = re.compile(
            r"[Rr]ef\s*:?\s*(\w+)\.(\w+)\s*([<>\-])\s*(\w+)\.(\w+)"
        )
        for m in ref_pattern.finditer(text):
            src_table, src_col, rel_char, tgt_table, tgt_col = (
                m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
            )
            rel_type_map = {">": "many_to_one", "<": "one_to_many", "-": "one_to_one"}
            for entity in entities:
                if entity["name"] == src_table:
                    already = any(
                        r["foreign_key"] == src_col and r["target_entity"] == tgt_table
                        for r in entity["relationships"]
                    )
                    if not already:
                        entity["relationships"].append({
                            "type": rel_type_map.get(rel_char, "many_to_one"),
                            "target_entity": tgt_table,
                            "foreign_key": src_col,
                            "on_delete": "CASCADE",
                            "description": "",
                        })
                    break

        if not entities:
            raise DataModelParseError("No Table definitions found in the DBML file.")

        model = {
            "version": 1,
            "project_mode": "new_project",
            "summary": f"Uploaded DBML schema with {len(entities)} table(s)",
            "entities": entities,
            "enums": enums,
            "change_log": [],
        }
        return DataModelGenerator._validate(model)

    @staticmethod
    def _split_columns(body: str) -> list[str]:
        lines = []
        current = ""
        depth = 0
        for char in body:
            if char == "(":
                depth += 1
                current += char
            elif char == ")":
                depth -= 1
                current += char
            elif char == "," and depth == 0:
                lines.append(current)
                current = ""
            else:
                current += char
        if current.strip():
            lines.append(current)
        return lines

    @staticmethod
    def _parse_sql_column(line: str) -> dict | None:
        col_match = re.match(
            r"[`\"\[]?(\w+)[`\"\]]?\s+(\w+(?:\([^)]*\))?)",
            line.strip(),
        )
        if not col_match:
            return None

        name = col_match.group(1)
        raw_type = col_match.group(2)

        upper_line = line.upper()
        is_pk = "PRIMARY KEY" in upper_line
        is_not_null = "NOT NULL" in upper_line
        is_unique = "UNIQUE" in upper_line

        default_match = re.search(r"DEFAULT\s+([^\s,]+)", line, re.IGNORECASE)
        default_val = default_match.group(1).strip("'\"") if default_match else None

        type_map = {
            "SERIAL": "INTEGER",
            "BIGSERIAL": "BIGINT",
            "INT": "INTEGER",
            "BOOL": "BOOLEAN",
            "TIMESTAMP": "DATETIME",
            "TIMESTAMPTZ": "DATETIME",
            "JSONB": "JSON",
        }
        mapped_type = type_map.get(raw_type.upper().split("(")[0], raw_type.upper())
        if "(" in raw_type:
            mapped_type = mapped_type.split("(")[0] + "(" + raw_type.split("(", 1)[1]

        return {
            "name": name,
            "type": mapped_type,
            "primary_key": is_pk,
            "nullable": not is_pk and not is_not_null,
            "unique": is_unique,
            "indexed": is_pk,
            "default": default_val,
            "description": "",
        }

    @staticmethod
    def _map_dbml_type(dbml_type: str) -> str:
        type_map = {
            "int": "INTEGER",
            "integer": "INTEGER",
            "bigint": "BIGINT",
            "float": "FLOAT",
            "decimal": "DECIMAL",
            "bool": "BOOLEAN",
            "boolean": "BOOLEAN",
            "varchar": "VARCHAR(255)",
            "text": "TEXT",
            "uuid": "UUID",
            "datetime": "DATETIME",
            "timestamp": "DATETIME",
            "date": "DATE",
            "json": "JSON",
            "jsonb": "JSON",
        }
        base = dbml_type.lower().split("(")[0]
        if base in type_map:
            if "(" in dbml_type:
                return type_map[base].split("(")[0] + "(" + dbml_type.split("(", 1)[1]
            return type_map[base]
        return dbml_type.upper()
