import httpx


class AzureDevOpsClient:
    def __init__(self, org_url: str, project: str, pat: str):
        self.org_url = org_url.rstrip("/")
        self.project = project
        self.auth = httpx.BasicAuth("", pat)
        self.api_version = "7.1"

    async def get_backlog_items(self, custom_query: str = "") -> list[dict]:
        wiql = custom_query or self._default_query()
        work_item_ids = await self._execute_wiql(wiql)
        if not work_item_ids:
            return []

        items = await self._get_work_items(work_item_ids)
        return self._build_hierarchy(items)

    def _default_query(self) -> str:
        return f"""
            SELECT [System.Id], [System.Title], [System.WorkItemType],
                   [System.Description], [Microsoft.VSTS.Common.AcceptanceCriteria],
                   [System.Parent]
            FROM WorkItems
            WHERE [System.TeamProject] = '{self.project}'
            AND [System.WorkItemType] IN ('Feature', 'User Story', 'Task')
            AND [System.State] <> 'Removed'
            ORDER BY [System.Id]
        """

    async def _execute_wiql(self, wiql: str) -> list[int]:
        url = f"{self.org_url}/{self.project}/_apis/wit/wiql?api-version={self.api_version}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"query": wiql},
                auth=self.auth,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["id"] for item in data.get("workItems", [])]

    async def _get_work_items(self, ids: list[int]) -> list[dict]:
        items = []
        for batch_start in range(0, len(ids), 200):
            batch_ids = ids[batch_start:batch_start + 200]
            ids_str = ",".join(str(i) for i in batch_ids)
            url = (
                f"{self.org_url}/{self.project}/_apis/wit/workitems"
                f"?ids={ids_str}"
                f"&$expand=relations"
                f"&api-version={self.api_version}"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, auth=self.auth, timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
                items.extend(data.get("value", []))
        return items

    def _build_hierarchy(self, items: list[dict]) -> list[dict]:
        parsed = []
        for item in items:
            fields = item.get("fields", {})
            parsed.append({
                "type": fields.get("System.WorkItemType", "").lower(),
                "id": str(item["id"]),
                "title": fields.get("System.Title", ""),
                "description": fields.get("System.Description", ""),
                "parent_id": str(fields.get("System.Parent", "")),
                "acceptance_criteria": fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""),
            })

        features = []
        stories_by_parent = {}
        tasks_by_parent = {}

        for item in parsed:
            if item["type"] == "feature":
                features.append({
                    "external_id": item["id"],
                    "title": item["title"],
                    "description": self._strip_html(item["description"]),
                    "user_stories": [],
                })
            elif item["type"] == "user story":
                parent = item["parent_id"]
                if parent not in stories_by_parent:
                    stories_by_parent[parent] = []
                stories_by_parent[parent].append({
                    "external_id": item["id"],
                    "title": item["title"],
                    "description": self._strip_html(item["description"]),
                    "acceptance_criteria": self._strip_html(item["acceptance_criteria"]),
                    "tasks": [],
                })
            elif item["type"] == "task":
                parent = item["parent_id"]
                if parent not in tasks_by_parent:
                    tasks_by_parent[parent] = []
                tasks_by_parent[parent].append({
                    "external_id": item["id"],
                    "title": item["title"],
                    "description": self._strip_html(item["description"]),
                })

        for feature in features:
            fid = feature["external_id"]
            feature["user_stories"] = stories_by_parent.get(fid, [])
            for story in feature["user_stories"]:
                sid = story["external_id"]
                story["tasks"] = tasks_by_parent.get(sid, [])

        return features

    @staticmethod
    def _strip_html(text: str) -> str:
        if not text:
            return ""
        import re
        clean = re.sub(r"<[^>]+>", "", text)
        return clean.strip()
