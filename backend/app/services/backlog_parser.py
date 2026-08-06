import io
import json
from pathlib import Path

import pandas as pd
import yaml


class BacklogParser:
    @staticmethod
    def _clean_id(value) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        s = str(value).strip()
        if s.endswith(".0"):
            s = s[:-2]
        if s.lower() in ("nan", "none", ""):
            return ""
        return s

    @staticmethod
    def _clean_str(value) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        s = str(value).strip()
        if s.lower() in ("nan", "none"):
            return ""
        return s

    def parse(self, content: bytes, filename: str) -> list[dict]:
        ext = Path(filename).suffix.lower()
        if ext in (".xlsx", ".xls"):
            return self._parse_excel(content)
        elif ext == ".csv":
            return self._parse_csv(content)
        elif ext == ".json":
            return self._parse_json(content)
        elif ext in (".yaml", ".yml"):
            return self._parse_yaml(content)
        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported: .xlsx, .csv, .json, .yaml")

    def _parse_excel(self, content: bytes) -> list[dict]:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        return self._parse_dataframe(df)

    def _parse_csv(self, content: bytes) -> list[dict]:
        text = content.decode("utf-8-sig")
        for sep in [",", ";", "\t"]:
            df = pd.read_csv(io.StringIO(text), sep=sep)
            if len(df.columns) > 1:
                break
        return self._parse_dataframe(df)

    def _parse_json(self, content: bytes) -> list[dict]:
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict) and "features" in data:
            return self._normalize_nested(data["features"])
        elif isinstance(data, list):
            if data and "work_item_type" in data[0]:
                return self._parse_flat_items(data)
            return self._normalize_nested(data)
        raise ValueError("Unrecognized JSON structure")

    def _parse_yaml(self, content: bytes) -> list[dict]:
        data = yaml.safe_load(content.decode("utf-8"))
        if isinstance(data, dict) and "features" in data:
            return self._normalize_nested(data["features"])
        elif isinstance(data, list):
            return self._normalize_nested(data)
        raise ValueError("Unrecognized YAML structure")

    def _parse_dataframe(self, df: pd.DataFrame) -> list[dict]:
        columns_lower = {c.lower().strip(): c for c in df.columns}

        if "type" in columns_lower or "work item type" in columns_lower:
            return self._parse_flat_df(df, columns_lower)
        return self._parse_hierarchical_df(df, columns_lower)

    def _parse_flat_df(self, df: pd.DataFrame, columns_lower: dict) -> list[dict]:
        type_col = columns_lower.get("type") or columns_lower.get("work item type")
        title_col = columns_lower.get("title") or columns_lower.get("name")
        desc_col = columns_lower.get("description") or columns_lower.get("desc")
        id_col = columns_lower.get("id") or columns_lower.get("work item id")
        parent_col = columns_lower.get("parent") or columns_lower.get("parent id")
        ac_col = columns_lower.get("acceptance criteria") or columns_lower.get("acceptance_criteria")

        items = []
        for _, row in df.iterrows():
            item_type = str(row.get(type_col, "")).lower().strip()
            items.append({
                "type": item_type,
                "id": self._clean_id(row.get(id_col)) if id_col else "",
                "title": self._clean_str(row.get(title_col)),
                "description": self._clean_str(row.get(desc_col)) if desc_col else "",
                "parent_id": self._clean_id(row.get(parent_col)) if parent_col else "",
                "acceptance_criteria": self._clean_str(row.get(ac_col)) if ac_col else "",
            })

        return self._build_hierarchy_from_flat(items)

    def _parse_hierarchical_df(self, df: pd.DataFrame, columns_lower: dict) -> list[dict]:
        feature_col = columns_lower.get("feature")
        story_col = columns_lower.get("user story") or columns_lower.get("story")
        task_col = columns_lower.get("task")
        desc_col = columns_lower.get("description") or columns_lower.get("desc")

        if not feature_col:
            raise ValueError("Cannot detect backlog structure. Ensure columns include 'Type' or 'Feature'.")

        features = {}
        for _, row in df.iterrows():
            feature_name = self._clean_str(row.get(feature_col))
            if not feature_name:
                continue

            if feature_name not in features:
                features[feature_name] = {"title": feature_name, "description": "", "user_stories": []}

            story_name = self._clean_str(row.get(story_col)) if story_col else ""
            if story_name:
                stories = features[feature_name]["user_stories"]
                story = next((s for s in stories if s["title"] == story_name), None)
                if not story:
                    story = {"title": story_name, "description": "", "tasks": []}
                    stories.append(story)

                task_name = self._clean_str(row.get(task_col)) if task_col else ""
                if task_name:
                    desc = self._clean_str(row.get(desc_col)) if desc_col else ""
                    story["tasks"].append({
                        "title": task_name,
                        "description": desc,
                    })

        return list(features.values())

    def _build_hierarchy_from_flat(self, items: list[dict]) -> list[dict]:
        by_id = {item["id"]: item for item in items if item["id"]}

        features = []
        stories_by_parent = {}
        tasks_by_parent = {}

        for item in items:
            if item["type"] in ("feature", "epic"):
                features.append({
                    "external_id": item["id"],
                    "title": item["title"],
                    "description": item["description"],
                    "user_stories": [],
                })
            elif item["type"] in ("user story", "story", "product backlog item"):
                parent_id = item["parent_id"]
                if parent_id not in stories_by_parent:
                    stories_by_parent[parent_id] = []
                stories_by_parent[parent_id].append({
                    "external_id": item["id"],
                    "title": item["title"],
                    "description": item["description"],
                    "acceptance_criteria": item.get("acceptance_criteria", ""),
                    "tasks": [],
                })
            elif item["type"] == "task":
                parent_id = item["parent_id"]
                if parent_id not in tasks_by_parent:
                    tasks_by_parent[parent_id] = []
                tasks_by_parent[parent_id].append({
                    "external_id": item["id"],
                    "title": item["title"],
                    "description": item["description"],
                })

        for feature in features:
            fid = feature["external_id"]
            feature["user_stories"] = stories_by_parent.get(fid, [])
            for story in feature["user_stories"]:
                sid = story["external_id"]
                story["tasks"] = tasks_by_parent.get(sid, [])

        return features

    def _normalize_nested(self, features: list[dict]) -> list[dict]:
        result = []
        for f in features:
            feature = {
                "external_id": f.get("external_id", f.get("id", "")),
                "title": f.get("title", f.get("name", "")),
                "description": f.get("description", ""),
                "user_stories": [],
            }
            for s in f.get("user_stories", f.get("stories", [])):
                story = {
                    "external_id": s.get("external_id", s.get("id", "")),
                    "title": s.get("title", s.get("name", "")),
                    "description": s.get("description", ""),
                    "acceptance_criteria": s.get("acceptance_criteria", ""),
                    "tasks": [],
                }
                for t in s.get("tasks", []):
                    story["tasks"].append({
                        "external_id": t.get("external_id", t.get("id", "")),
                        "title": t.get("title", t.get("name", "")),
                        "description": t.get("description", ""),
                    })
                feature["user_stories"].append(story)
            result.append(feature)
        return result

    def _parse_flat_items(self, items: list[dict]) -> list[dict]:
        converted = []
        for item in items:
            converted.append({
                "type": item.get("work_item_type", "").lower(),
                "id": str(item.get("id", "")),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "parent_id": str(item.get("parent_id", "")),
                "acceptance_criteria": item.get("acceptance_criteria", ""),
            })
        return self._build_hierarchy_from_flat(converted)
