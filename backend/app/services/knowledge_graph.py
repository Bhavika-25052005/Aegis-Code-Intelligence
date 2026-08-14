"""
Knowledge Graph Service.
Claude reads the workspace and generates the full graph (nodes + descriptions + edges).
One call per generation. Node descriptions are stored so clicks are instant.
"""
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VALID_NODE_TYPES = {"file", "service", "model", "api", "controller", "frontend", "task", "acceptance_criterion", "test", "class"}
VALID_EDGE_TYPES = {"IMPORTS", "DEPENDS_ON", "USES", "CALLS", "MODIFIES", "IMPLEMENTS", "VALIDATED_BY", "TESTS", "DEPENDS_ON_TASK", "CONTAINS"}


class KnowledgeGraphService:

    async def generate_initial_graph(self, project, story, db: AsyncSession) -> dict:
        """
        Claude analyzes the workspace and generates the full knowledge graph.
        Each node gets a one-sentence description. Edges are only created when
        Claude can verify them by reading code.
        """
        from app.models.project import RepositoryFile, GraphNode, GraphEdge
        from app.services.claude_runner import ClaudeRunner

        project_id = project.id
        story_id = story.id
        new_version = (getattr(story, "graph_version", 0) or 0) + 1
        workspace = project.workspace_path or ""

        # Clear existing graph
        await db.execute(delete(GraphNode).where(GraphNode.project_id == project_id, GraphNode.story_id == story_id))
        await db.execute(delete(GraphEdge).where(GraphEdge.project_id == project_id, GraphEdge.story_id == story_id))

        # Load context
        repo_files_q = await db.execute(select(RepositoryFile).where(RepositoryFile.project_id == project_id))
        repo_files = repo_files_q.scalars().all()

        req = self._load_json(story.requirement_analysis)
        plan = self._load_json(story.implementation_plan)

        # Build a concise file listing for Claude
        file_lines = []
        for rf in repo_files[:60]:
            file_lines.append(f"  {rf.relative_path} [{rf.category}]")
        file_listing = "\n".join(file_lines) if file_lines else "  (no indexed files)"

        # Planned files from implementation plan
        planned = []
        for c in plan.get("planned_changes", []):
            p = c.get("path", "")
            if p:
                planned.append(f"  {p} ({c.get('action','?')}) - {c.get('purpose','')[:60]}")
        planned_block = "\n".join(planned[:20]) if planned else "  (none)"

        # Tasks — explicit IDs for Claude to reuse exactly
        tasks_block = ""
        for t in (plan.get("task_plan") or [])[:15]:
            order = t.get("execution_order", "?")
            deps = ", ".join(f"T{d}" for d in (t.get("depends_on") or []))
            files = ", ".join(
                (c.get("path", "") if isinstance(c, dict) else str(c))
                for c in (t.get("related_files") or [])[:3]
            )
            tasks_block += (
                f"  task:T{order} | title: {t.get('task_title','')} "
                f"| depends_on: {deps or 'none'} | modifies: {files or 'see planned changes'}\n"
            )

        # ACs
        acs = req.get("acceptance_criteria", [])
        acs_block = "\n".join(f"  AC{i+1}: {str(a)[:100]}" for i, a in enumerate(acs[:15]))

        prompt = f"""You are generating a Knowledge Graph for the Aegis platform. Analyze this project and return a graph that visualises the architecture and relationships.

## Project context
Story: {story.title}
Requirement summary: {req.get('summary', '')[:300]}
Work summary: {plan.get('work_summary', '')[:300]}

## Repository files (already indexed)
{file_listing}

## Planned file changes
{planned_block}

## Implementation tasks
{tasks_block}

## Acceptance Criteria
{acs_block}

## Your task
1. Use Read and Glob tools to inspect the key source files listed above.
2. Identify the main components, their types, and how they connect.
3. Return a graph that shows architecture clearly.

Node types allowed:
  file | service | model | api | controller | frontend | class | acceptance_criterion | task

Edge types allowed:
  IMPORTS | DEPENDS_ON | DEPENDS_ON_TASK | USES | CALLS | MODIFIES | CONTAINS | IMPLEMENTS

Node ID format:
  - Code components: "<type>:<CamelCaseName>" — e.g. "service:PrescriptionService"
  - Acceptance criteria: "ac:AC1", "ac:AC2" etc. (use the AC numbers from the list above)
  - Tasks: "task:T1", "task:T2" etc. (use the task execution order numbers from the list above)

Rules:
- Maximum 45 nodes total.
- description: ONE sentence only. What it does. No filler.
- For acceptance_criterion nodes: label = "AC1", description = the criterion text (max 80 chars).
- For task nodes: label = "T1", description = the task title.
- INCLUDE ALL tasks from the implementation tasks list above as task nodes.
- INCLUDE ALL acceptance criteria from the list above as acceptance_criterion nodes.
- Connect task nodes: use DEPENDS_ON_TASK edges where depends_on is not empty.
- Connect tasks to code files using MODIFIES edges (from planned changes above).
- Connect tasks to ACs using IMPLEMENTS edges.
- For code component edges: ONLY create edges you verified by reading the code files.
- DO NOT include test nodes.
- Focus on: tasks → files they modify, tasks → ACs they implement, code architecture (services/models/APIs).

Return ONLY valid JSON — no markdown, no explanation, no text before or after the JSON:
{{
  "nodes": [
    {{
      "id": "service:PrescriptionService",
      "type": "service",
      "label": "PrescriptionService",
      "file": "backend/services/prescription_service.py",
      "description": "Handles prescription creation, validation and retrieval."
    }},
    {{
      "id": "model:PrescriptionModel",
      "type": "model",
      "label": "PrescriptionModel",
      "file": "backend/models/prescription.py",
      "description": "SQLAlchemy model representing a prescription record."
    }},
    {{
      "id": "api:PrescriptionRouter",
      "type": "api",
      "label": "PrescriptionRouter",
      "file": "backend/api/prescriptions.py",
      "description": "FastAPI router exposing CRUD endpoints for prescriptions."
    }},
    {{
      "id": "ac:AC1",
      "type": "acceptance_criterion",
      "label": "AC1",
      "file": null,
      "description": "Doctor can create a prescription with at least one medication item."
    }},
    {{
      "id": "task:T1",
      "type": "task",
      "label": "T1",
      "file": null,
      "description": "Create Prescription model with doctor, patient and items relationships."
    }},
    {{
      "id": "task:T2",
      "type": "task",
      "label": "T2",
      "file": null,
      "description": "Create prescription API endpoints with auth and validation."
    }}
  ],
  "edges": [
    {{
      "source": "api:PrescriptionRouter",
      "target": "service:PrescriptionService",
      "type": "CALLS"
    }},
    {{
      "source": "service:PrescriptionService",
      "target": "model:PrescriptionModel",
      "type": "USES"
    }},
    {{
      "source": "task:T1",
      "target": "model:PrescriptionModel",
      "type": "MODIFIES"
    }},
    {{
      "source": "task:T2",
      "target": "api:PrescriptionRouter",
      "type": "MODIFIES"
    }},
    {{
      "source": "task:T2",
      "target": "task:T1",
      "type": "DEPENDS_ON_TASK"
    }},
    {{
      "source": "task:T1",
      "target": "ac:AC1",
      "type": "IMPLEMENTS"
    }}
  ]
}}"""

        # Sanitize prompt — replace Unicode chars that Windows CP1252 can't encode
        safe_prompt = (
            prompt
            .replace("→", "->")   # →
            .replace("←", "<-")   # ←
            .replace("—", "-")    # —
            .replace("–", "-")    # –
            .replace("•", "*")    # •
            .replace("‘", "'").replace("’", "'")   # curly quotes
            .replace("“", '"').replace("”", '"')   # curly double quotes
        )
        budget = min(getattr(project, "claude_max_budget_usd", 3.0), 3.0)
        runner = ClaudeRunner(workspace_path=workspace, max_budget_usd=budget, allowed_tools="Read,Glob,Grep")
        result = await runner.execute(safe_prompt)

        # ── Save Claude's raw output for debugging ───────────────────────────
        raw_output = result.output or ""
        logger.info("=== CLAUDE GRAPH RAW OUTPUT (project=%s story=%s) ===\n%s\n=== END ===",
                    project_id, story_id, raw_output[:8000])
        try:
            debug_path = Path(workspace) / ".aegis_graph_debug.json" if workspace else None
            if debug_path:
                debug_path.write_text(json.dumps({
                    "project_id": project_id, "story_id": story_id,
                    "generated_at": datetime.utcnow().isoformat(),
                    "success": result.success,
                    "raw_output": raw_output,
                }, indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info("Claude graph debug saved to: %s", debug_path)
        except Exception as exc:
            logger.warning("Could not save graph debug file: %s", exc)
        # ────────────────────────────────────────────────────────────────────

        if not result.success:
            logger.warning("Claude graph generation failed: %s", result.error)
            return await self._fallback_generate(project, story, repo_files, req, plan, new_version, db)

        parsed = self._parse_json(raw_output)
        if not parsed or not parsed.get("nodes"):
            logger.warning("Claude graph returned no valid JSON, using fallback")
            return await self._fallback_generate(project, story, repo_files, req, plan, new_version, db)

        # Persist Claude's graph
        nodes_added = 0
        edges_added = 0

        for n in parsed.get("nodes", []):
            ntype = str(n.get("type", "file")).lower()
            if ntype not in VALID_NODE_TYPES:
                ntype = "file"
            node_key = str(n.get("id", ""))
            if not node_key:
                continue
            db.add(GraphNode(
                id=str(uuid.uuid4()),
                project_id=project_id,
                story_id=story_id,
                node_key=node_key,
                node_type=ntype,
                label=str(n.get("label", node_key.split(":")[-1]))[:100],
                file_path=n.get("file") or None,
                metadata_json=json.dumps({
                    "description": str(n.get("description", ""))[:300],
                    "source": "claude",
                }),
                graph_version=new_version,
            ))
            nodes_added += 1

        node_keys = {str(n.get("id", "")) for n in parsed.get("nodes", [])}

        for e in parsed.get("edges", []):
            src = str(e.get("source", ""))
            tgt = str(e.get("target", ""))
            rel = str(e.get("type", "")).upper()
            if not src or not tgt or rel not in VALID_EDGE_TYPES:
                continue
            if src not in node_keys or tgt not in node_keys or src == tgt:
                continue
            db.add(GraphEdge(
                id=str(uuid.uuid4()),
                project_id=project_id,
                story_id=story_id,
                source_key=src,
                target_key=tgt,
                relation_type=rel,
                metadata_json="{}",
                graph_version=new_version,
            ))
            edges_added += 1

        story.graph_status = "current"
        story.graph_version = new_version
        story.graph_generated_at = datetime.utcnow()
        story.graph_fingerprint = hashlib.sha256(
            f"{project_id}:{story_id}:{new_version}".encode()
        ).hexdigest()[:32]

        await db.commit()
        return {"status": "current", "version": new_version, "node_count": nodes_added, "edge_count": edges_added}

    async def _fallback_generate(self, project, story, repo_files, req, plan, version, db) -> dict:
        """Deterministic fallback if Claude is unavailable."""
        from app.models.project import GraphNode, GraphEdge

        project_id = project.id
        story_id = story.id
        nodes = {}
        edges = []

        for rf in repo_files[:40]:
            ntype = _infer_node_type(rf.relative_path, rf.category)
            key = f"file:{_short_label(rf.relative_path)}"
            nodes[key] = dict(node_key=key, node_type=ntype, label=_short_label(rf.relative_path),
                              file_path=rf.relative_path, metadata_json=json.dumps({"description": "", "source": "fallback"}))

        ac_keys = {}
        for i, ac in enumerate(req.get("acceptance_criteria", [])):
            key = f"ac:AC{i+1}"
            ac_keys[f"AC{i+1}"] = key
            nodes[key] = dict(node_key=key, node_type="acceptance_criterion", label=f"AC{i+1}",
                              file_path=None, metadata_json=json.dumps({"description": str(ac)[:200], "source": "fallback"}))

        for t in (plan.get("task_plan") or []):
            tid = str(t.get("task_id", ""))
            if not tid:
                continue
            key = f"task:T{t.get('execution_order', tid)}"
            nodes[key] = dict(node_key=key, node_type="task", label=t.get("task_title", key)[:50],
                              file_path=None, metadata_json=json.dumps({"description": t.get("approach", "")[:200], "source": "fallback"}))

        seen = set()
        for n in nodes.values():
            db.add(GraphNode(id=str(uuid.uuid4()), project_id=project_id, story_id=story_id,
                             graph_version=version, **n))
        for e in edges:
            k = (e["source_key"], e["target_key"], e["relation_type"])
            if k not in seen:
                seen.add(k)
                db.add(GraphEdge(id=str(uuid.uuid4()), project_id=project_id, story_id=story_id,
                                 graph_version=version, **e))

        story.graph_status = "current"
        story.graph_version = version
        story.graph_generated_at = datetime.utcnow()
        story.graph_fingerprint = hashlib.sha256(f"{project_id}:{story_id}:{version}:fallback".encode()).hexdigest()[:32]
        await db.commit()
        return {"status": "current", "version": version, "node_count": len(nodes), "edge_count": len(edges)}

    async def get_graph(self, project_id: str, story_id: str, focus_node: Optional[str],
                        depth: int, node_types: Optional[list], search: Optional[str], db: AsyncSession) -> dict:
        from app.models.project import GraphNode, GraphEdge

        nodes_q = await db.execute(select(GraphNode).where(GraphNode.project_id == project_id, GraphNode.story_id == story_id))
        all_nodes = nodes_q.scalars().all()
        edges_q = await db.execute(select(GraphEdge).where(GraphEdge.project_id == project_id, GraphEdge.story_id == story_id))
        all_edges = edges_q.scalars().all()

        node_map = {n.node_key: n for n in all_nodes}
        adj: dict = {n.node_key: set() for n in all_nodes}
        for e in all_edges:
            if e.source_key in adj: adj[e.source_key].add(e.target_key)
            if e.target_key in adj: adj[e.target_key].add(e.source_key)

        if focus_node and focus_node in node_map:
            visible: set = set()
            frontier = {focus_node}
            for _ in range(depth):
                nxt = set()
                for n in frontier:
                    visible.add(n)
                    nxt.update(adj.get(n, set()) - visible)
                frontier = nxt
            visible.update(frontier)
        else:
            visible = set(node_map.keys())

        if node_types:
            visible = {k for k in visible if node_map[k].node_type in node_types}
        if search:
            s = search.lower()
            visible = {k for k in visible if s in node_map[k].label.lower() or s in (node_map[k].file_path or "").lower()}

        out_nodes = []
        for key in visible:
            n = node_map[key]
            try:
                meta = json.loads(n.metadata_json) if n.metadata_json else {}
            except Exception:
                meta = {}
            out_nodes.append({"id": n.node_key, "type": n.node_type, "label": n.label, "file": n.file_path, "metadata": meta})

        out_edges = [{"source": e.source_key, "target": e.target_key, "type": e.relation_type}
                     for e in all_edges if e.source_key in visible and e.target_key in visible]

        return {"nodes": out_nodes, "edges": out_edges, "stats": {"nodes": len(out_nodes), "edges": len(out_edges)}}

    async def analyze_impact(self, project_id: str, story_id: str, node_key: str, depth: int, db: AsyncSession) -> dict:
        from app.models.project import GraphNode, GraphEdge

        nodes_q = await db.execute(select(GraphNode).where(GraphNode.project_id == project_id, GraphNode.story_id == story_id))
        node_map = {n.node_key: n for n in nodes_q.scalars().all()}
        if node_key not in node_map:
            return {"error": f"Node '{node_key}' not found."}

        edges_q = await db.execute(select(GraphEdge).where(GraphEdge.project_id == project_id, GraphEdge.story_id == story_id))
        all_edges = list(edges_q.scalars().all())

        out_adj: dict = {k: [] for k in node_map}
        in_adj: dict = {k: [] for k in node_map}
        for e in all_edges:
            if e.source_key in out_adj: out_adj[e.source_key].append(e.target_key)
            if e.target_key in in_adj: in_adj[e.target_key].append(e.source_key)

        def bfs(start: str, adj: dict, d: int) -> set:
            vis: set = set()
            frontier = {start}
            for _ in range(d):
                nxt = set()
                for n in frontier:
                    for nb in adj.get(n, []):
                        if nb not in vis and nb != start: nxt.add(nb)
                vis.update(frontier - {start}); frontier = nxt - vis
            vis.update(frontier - {start}); vis.discard(start)
            return vis

        deps = bfs(node_key, out_adj, depth)
        consumers = bfs(node_key, in_adj, depth)
        affected = deps | consumers

        file_types = {"file", "service", "model", "api", "controller", "frontend"}
        affected_files = [k for k in affected if node_map[k].node_type in file_types]
        related_tasks = [k for k in affected if node_map[k].node_type == "task"]
        related_acs = [k for k in affected if node_map[k].node_type == "acceptance_criterion"]
        related_tests = [k for k in affected if node_map[k].node_type == "test"]

        types_hit = {node_map[k].node_type for k in affected}
        boundary = {"api", "model", "service"}
        crosses = len(types_hit & boundary) >= 2
        n_files = len(affected_files)
        risk = "HIGH" if n_files > 8 or (crosses and n_files > 4) else "MEDIUM" if n_files >= 3 or crosses else "LOW"

        def detail(k: str) -> dict:
            n = node_map.get(k)
            return {"key": k, "label": n.label if n else k, "type": n.node_type if n else "", "file": n.file_path if n else None}

        sel = node_map[node_key]
        return {
            "selected_node": {"key": node_key, "label": sel.label, "type": sel.node_type, "file": sel.file_path},
            "direct_dependencies": [detail(k) for k in bfs(node_key, out_adj, 1)],
            "direct_consumers": [detail(k) for k in bfs(node_key, in_adj, 1)],
            "affected_files": [detail(k) for k in affected_files],
            "related_tasks": [detail(k) for k in related_tasks],
            "acceptance_criteria": [detail(k) for k in related_acs],
            "related_tests": [detail(k) for k in related_tests],
            "impact_counts": {"files": n_files, "tasks": len(related_tasks), "acs": len(related_acs), "tests": len(related_tests)},
            "risk": risk,
        }

    async def mark_stale(self, project_id: str, story_id: str, db: AsyncSession):
        from app.models.backlog import UserStory
        result = await db.execute(select(UserStory).where(UserStory.id == story_id))
        story = result.scalar_one_or_none()
        if story and getattr(story, "graph_status", "") == "current":
            story.graph_status = "stale"
            await db.commit()

    async def enhance_with_claude(self, project, story, workspace: str, db: AsyncSession) -> dict:
        """Removed — generation now uses Claude directly. This is a no-op kept for compatibility."""
        return {"edges_added": 0, "message": "Generation already uses Claude. Click Regenerate to refresh."}

    def _parse_json(self, output: str) -> Optional[dict]:
        if not output.strip():
            return None
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL | re.IGNORECASE)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except Exception:
                pass
        start, end = output.find("{"), output.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(output[start:end + 1])
            except Exception:
                pass
        return None

    @staticmethod
    def _load_json(val: str) -> dict:
        try:
            return json.loads(val) if val else {}
        except Exception:
            return {}


def _infer_node_type(path: str, category: str = "source") -> str:
    p = path.lower().replace("\\", "/")
    stem = Path(p).stem
    if category == "test" or "/test" in p or stem.startswith("test_") or stem.endswith("_test"):
        return "test"
    if any(x in p for x in ["/api/", "/apis/", "api.py", "/routers/", "router.py", "/routes/"]):
        return "api"
    if any(x in p for x in ["/controllers/", "controller.py"]):
        return "controller"
    if any(x in p for x in ["/services/", "service.py", "_service.py"]):
        return "service"
    if any(x in p for x in ["/models/", "model.py", "_model.py", "/schemas/", "schema.py", "/repositories/"]):
        return "model"
    if any(x in p for x in [".vue", ".tsx", ".jsx", ".svelte", "/components/", "/views/"]):
        return "frontend"
    return "file"


def _short_label(path: str) -> str:
    name = Path(path).stem
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts) if len(parts) > 1 else name
