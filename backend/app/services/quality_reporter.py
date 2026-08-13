"""
Day 4 — Quality Traceability + PDF Report Service.

Responsibilities:
- build_summary: deterministic test counts from persisted Day 3 test_plan + TestRun records
- ensure_traceability: reuse Day 3 mappings; ask Claude once for unmapped tests; persist results
- filter_tests: pure in-memory filtering (no Claude calls)
- generate_pdf: compact ReportLab PDF of currently-filtered test view
"""

import hashlib
import json
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AC palette — colors cycle if criteria > palette length
# ---------------------------------------------------------------------------
AC_COLORS = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#06b6d4",  # cyan
    "#f97316",  # orange
    "#84cc16",  # lime
    "#ec4899",  # pink
    "#6366f1",  # indigo
]


def _ac_color(index: int) -> str:
    return AC_COLORS[index % len(AC_COLORS)]


def _build_ac_legend(acceptance_criteria: list[str]) -> list[dict]:
    """Return [{id, text, color}, ...] from the approved AC list."""
    return [
        {
            "id": f"AC{i + 1}",
            "text": criterion.strip(),
            "color": _ac_color(i),
        }
        for i, criterion in enumerate(acceptance_criteria)
    ]


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class QualityReporter:
    """All Day 4 quality reporting logic in one place."""

    def build_summary(self, story, test_runs: list | None = None) -> dict:
        """
        Return deterministic test counts from Day 3 test_plan + TestRun records.

        Strategy:
        - test_plan entries drive traceability-level counts (unit, integration, system,
          regression, custom) because they carry source_type and scope.
        - TestRun records carry authoritative pass/fail counts and are the source of
          truth for integration/quality/regression runs that were NOT written back to
          test_plan as individual entries.
        - For pass/fail we use TestRun totals when available (accurate), otherwise fall
          back to test_plan status fields.
        """
        test_plan = self._load_test_plan(story)
        tests = test_plan.get("tests", [])

        # ── Step 1: count by type from test_plan (deduped) ──────────────────
        seen_ids: set = set()
        unique_tests: list[dict] = []
        for t in tests:
            tid = t.get("test_id") or t.get("test_name") or json.dumps(t, sort_keys=True)
            if tid not in seen_ids:
                seen_ids.add(tid)
                unique_tests.append(t)

        # integration and system are merged into one display bucket
        type_counts: dict[str, int] = {
            "unit": 0, "integration_system": 0,
            "regression": 0, "custom": 0,
        }
        custom_passed = 0  # track custom test pass count separately

        for t in unique_tests:
            scope = (t.get("scope") or t.get("test_type") or t.get("type") or "unit").lower()
            source_type = t.get("source_type", "")
            status = (t.get("status") or "generated").lower()

            if source_type == "user_requested":
                type_counts["custom"] += 1
                if status == "passed":
                    custom_passed += 1
            elif scope in ("integration", "system", "quality"):
                type_counts["integration_system"] += 1
            elif scope == "regression":
                type_counts["regression"] += 1
            else:
                type_counts["unit"] += 1

        # ── Step 2: pass/fail from TestRun records (authoritative for executed tests) ──
        passed = 0
        failed = 0
        run_by_type: dict[str, int] = {}

        if test_runs:
            for run in test_runs:
                passed += getattr(run, "passed_tests", 0)
                failed += getattr(run, "failed_tests", 0)
                t = getattr(run, "test_type", "unit")
                # merge integration/system/quality into one bucket
                key = "integration_system" if t in ("integration", "system", "quality") else t
                run_by_type[key] = run_by_type.get(key, 0) + getattr(run, "total_tests", 0)

            # Use TestRun totals for unit and integration_system (authoritative)
            if run_by_type.get("unit", 0) > 0:
                type_counts["unit"] = run_by_type["unit"]
            if run_by_type.get("integration_system", 0) > 0:
                type_counts["integration_system"] = run_by_type["integration_system"]
            if run_by_type.get("regression", 0) > 0:
                type_counts["regression"] = run_by_type["regression"]

            # Add custom tests to passed total (they run via API, not TestRun records)
            passed += custom_passed
        else:
            # Fall back to test_plan status fields
            for t in unique_tests:
                s = (t.get("status") or "generated").lower()
                if s == "passed":
                    passed += 1
                elif s in ("failed", "needs_human_review"):
                    failed += 1

        total = (
            type_counts["unit"]
            + type_counts["integration_system"]
            + type_counts["regression"]
            + type_counts["custom"]
        )
        if total == 0:
            total = len(unique_tests)

        return {
            "unit": type_counts["unit"],
            "integration_system": type_counts["integration_system"],
            "regression": type_counts["regression"],
            "custom": type_counts["custom"],
            "total": total,
            "passed": passed,
            "failed": failed,
        }

    def compute_snapshot_hash(self, story, test_runs: list | None = None) -> str:
        """Hash the inputs that determine the quality snapshot so we know when to recompute."""
        run_key = json.dumps(
            sorted([
                (getattr(r, "test_type", ""), getattr(r, "total_tests", 0),
                 getattr(r, "passed_tests", 0), getattr(r, "failed_tests", 0))
                for r in (test_runs or [])
            ])
        )
        raw = (story.test_plan or "") + (story.requirement_analysis or "") + run_key
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def load_snapshot(self, story, expected_hash: str) -> dict | None:
        """Return cached snapshot if hash matches, else None."""
        if (
            story.quality_snapshot
            and story.quality_snapshot_hash == expected_hash
        ):
            try:
                return json.loads(story.quality_snapshot)
            except Exception:
                return None
        return None

    def save_snapshot(self, story, snapshot: dict, snapshot_hash: str):
        """Persist the computed snapshot to the story object (caller must commit)."""
        story.quality_snapshot = json.dumps(snapshot)
        story.quality_snapshot_hash = snapshot_hash

    async def ensure_traceability(
        self,
        story,
        requirement: dict,
        workspace_path: str,
        test_runs: list | None = None,
    ) -> dict:
        """
        Build full traceability data with caching.

        Mapping strategy (in priority order):
        1. Already has 'criteria' set — skip.
        2. Extract AC number from test_id pattern: REQ-AC-{N}-* or REQ-FR-{N}-* → AC{N}.
        3. Text-match source_text against approved AC list (substring match).
        4. Claude read-only inspection for any tests still unmapped (only when explicitly
           requested via the verify-traceability endpoint, not on every GET).

        Returns: {ac_legend, tests, summary, snapshot_hash}
        """
        acceptance_criteria = requirement.get("acceptance_criteria", [])
        ac_legend = _build_ac_legend(acceptance_criteria)

        # ── Check cache first ───────────────────────────────────────────────
        snapshot_hash = self.compute_snapshot_hash(story, test_runs)
        cached = self.load_snapshot(story, snapshot_hash)
        if cached is not None:
            logger.debug("Quality snapshot cache hit for story %s", story.id)
            return cached

        # ── Cache miss — compute from scratch ──────────────────────────────
        test_plan = self._load_test_plan(story)
        tests = test_plan.get("tests", [])
        changed = False

        for t in tests:
            if t.get("criteria"):
                continue  # already mapped, skip

            # ── Strategy 1: parse AC number from test_id ────────────────────
            test_id = t.get("test_id") or ""
            # Patterns: REQ-AC-{N}-{seq}, REQ-FR-{N}-{seq}, CUSTOM-{N}, INT-{N}
            m = re.match(r"REQ-(?:AC|FR|EC)-(\d+)-", test_id)
            if m:
                ac_num = int(m.group(1))
                ac_id = f"AC{ac_num}"
                # Validate AC exists in legend
                if any(a["id"] == ac_id for a in ac_legend):
                    t["criteria"] = [ac_id]
                    t["mapping_source"] = "test_id_pattern"
                    changed = True
                    continue

            # ── Strategy 2: source_text substring match ──────────────────────
            source_text = (t.get("source_text") or "").strip().lower()
            if source_text:
                matched_ids = []
                for ac in ac_legend:
                    ac_lower = ac["text"].lower()
                    if (
                        source_text == ac_lower
                        or (len(source_text) > 20 and source_text[:40] in ac_lower)
                        or (len(ac_lower) > 20 and ac_lower[:40] in source_text)
                    ):
                        matched_ids.append(ac["id"])
                if matched_ids:
                    t["criteria"] = matched_ids
                    t["mapping_source"] = "source_text_match"
                    changed = True
                    continue

            # ── Strategy 3: keyword matching for edge cases / schema tests ────
            # Skip custom/user_requested tests — they don't map to ACs
            if t.get("source_type") == "user_requested":
                continue

            source_text = (t.get("source_text") or "").strip().lower()
            test_id_lower = (t.get("test_id") or "").lower()
            search_str = source_text or test_id_lower

            if search_str:
                keyword_map = self._build_keyword_map(ac_legend)
                matched_ids = []
                for ac_id, keywords in keyword_map.items():
                    if any(kw in search_str for kw in keywords):
                        matched_ids.append(ac_id)
                if matched_ids:
                    t["criteria"] = matched_ids
                    t["mapping_source"] = "keyword_match"
                    changed = True

        # Persist updated test_plan if mapping changed
        if changed:
            test_plan["tests"] = tests
            story.test_plan = json.dumps(test_plan)
            story.test_updated_at = datetime.utcnow()
            # Recompute hash after test_plan change
            snapshot_hash = self.compute_snapshot_hash(story, test_runs)

        summary = self.build_summary(story, test_runs=test_runs)

        result = {
            "ac_legend": ac_legend,
            "tests": tests,
            "summary": summary,
            "snapshot_hash": snapshot_hash,
            "computed_at": datetime.utcnow().isoformat(),
        }

        # Save snapshot (caller must commit)
        self.save_snapshot(story, result, snapshot_hash)
        return result

    async def ensure_traceability_with_claude(
        self,
        story,
        requirement: dict,
        workspace_path: str,
        test_runs: list | None = None,
    ) -> dict:
        """
        Like ensure_traceability but also invokes Claude for tests still unmapped
        after pattern + text-match. Only called from the verify-traceability endpoint.
        Invalidates the cache so next GET recomputes.
        """
        # First run the deterministic pass
        result = await self.ensure_traceability(story, requirement, workspace_path, test_runs)
        test_plan = self._load_test_plan(story)
        tests = test_plan.get("tests", [])
        ac_legend = result["ac_legend"]

        still_unmapped = [
            t for t in tests
            if not t.get("criteria") and t.get("file")
        ]

        if still_unmapped and workspace_path:
            files_to_inspect = list({t.get("file", "") for t in still_unmapped if t.get("file")})
            if files_to_inspect:
                try:
                    new_mappings = await self._claude_verify_mappings(
                        files_to_inspect, ac_legend, workspace_path
                    )
                    mapping_by_name: dict[str, list[str]] = {
                        m.get("test_name", ""): m.get("criteria", [])
                        for m in new_mappings
                    }
                    for t in tests:
                        name = t.get("test_name") or t.get("test_id") or ""
                        if name in mapping_by_name and not t.get("criteria"):
                            t["criteria"] = mapping_by_name[name]
                            t["mapping_source"] = "claude_verified"
                except Exception as exc:
                    logger.warning("Claude traceability verification failed: %s", exc)

            test_plan["tests"] = tests
            story.test_plan = json.dumps(test_plan)
            story.test_updated_at = datetime.utcnow()

        # Invalidate cache so next GET recomputes with new mappings
        story.quality_snapshot = ""
        story.quality_snapshot_hash = ""

        summary = self.build_summary(story, test_runs=test_runs)
        return {"ac_legend": ac_legend, "tests": tests, "summary": summary}

    async def _claude_verify_mappings(
        self,
        test_files: list[str],
        ac_legend: list[dict],
        workspace_path: str,
    ) -> list[dict]:
        """Ask Claude (read-only) to map test functions to AC IDs. Returns list of mappings."""
        from app.services.claude_runner import ClaudeRunner

        ac_lines = "\n".join(f"{ac['id']}: {ac['text']}" for ac in ac_legend)
        files_list = "\n".join(f"- {f}" for f in test_files[:20])  # cap at 20 files

        prompt = f"""You are verifying TEST TRACEABILITY only.

APPROVED ACCEPTANCE CRITERIA
{ac_lines}

Read the following existing test files in the workspace:
{files_list}

For each test function/class found in those files:
- return its test name (function name)
- return its file path
- return zero, one or multiple matching AC IDs from the list above
- only map when the test actually verifies that acceptance criterion
- do not infer coverage from filename alone
- do not modify source or test files
- do not run tests
- do not invent acceptance criteria not in the list above

Return ONLY a strict JSON object as the last thing in your response:
{{
  "mappings": [
    {{
      "test_name": "test_missing_dosage",
      "file": "tests/unit/test_prescription.py",
      "criteria": ["AC3"]
    }}
  ]
}}
"""
        runner = ClaudeRunner(
            workspace_path=workspace_path,
            max_budget_usd=1.0,
            allowed_tools="Read,Glob,Grep",
        )
        result = await runner.execute(prompt)
        if not result.success:
            logger.warning("Claude traceability verification returned error: %s", result.error[:200])
            return []

        # Parse JSON from Claude output
        output = result.output or ""
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL | re.IGNORECASE)
        if fenced:
            output = fenced.group(1)
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            start, end = output.find("{"), output.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(output[start : end + 1])
                except json.JSONDecodeError:
                    return []
            else:
                return []
        return data.get("mappings", []) if isinstance(data, dict) else []

    def filter_tests(
        self,
        traceability: dict,
        search: Optional[str] = None,
        criterion: Optional[str] = None,
        test_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Pure deterministic filtering — no Claude calls ever."""
        tests = traceability.get("tests", [])
        results = []

        search_lower = search.lower().strip() if search else None
        criterion_upper = criterion.upper().strip() if criterion else None
        type_lower = test_type.lower().strip() if test_type else None
        status_lower = status.lower().strip() if status else None

        for t in tests:
            name = (t.get("test_name") or t.get("test_id") or "").lower()
            file_path = (t.get("file") or "").lower()
            scope = (t.get("scope") or t.get("test_type") or t.get("type") or "unit").lower()
            t_status = (t.get("status") or "generated").lower()
            criteria = [c.upper() for c in (t.get("criteria") or [])]

            if search_lower and search_lower not in name and search_lower not in file_path:
                continue
            if criterion_upper and criterion_upper not in criteria:
                continue
            if type_lower and scope != type_lower:
                continue
            if status_lower:
                if status_lower == "needs_review" and t_status != "needs_human_review":
                    continue
                elif status_lower not in ("needs_review",) and t_status != status_lower:
                    continue

            results.append(t)

        return results

    def generate_pdf(
        self,
        project,
        feature,
        story,
        requirement: dict,
        tests: list[dict],
        active_filters: dict,
        output_path: str,
    ) -> str:
        """Generate compact traceability PDF using ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, KeepTogether,
        )
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        acceptance_criteria = requirement.get("acceptance_criteria", [])
        ac_legend = _build_ac_legend(acceptance_criteria)
        ac_by_id = {ac["id"]: ac for ac in ac_legend}

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceAfter=4)
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceAfter=3)
        body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, spaceAfter=2)
        small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, spaceAfter=2)

        story_content = []

        # ── Header ──────────────────────────────────────────────────────────
        story_content.append(Paragraph("AEGIS TEST TRACEABILITY REPORT", h1))
        story_content.append(Spacer(1, 3 * mm))

        meta_data = [
            ["Project", getattr(project, "name", "—")],
            ["Feature", getattr(feature, "title", "—") if feature else "—"],
            ["User Story", getattr(story, "title", "—")],
            ["Quality Gate", getattr(story, "test_status", "—").replace("_", " ").title()],
            ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
        ]
        meta_table = Table(meta_data, colWidths=[40 * mm, 130 * mm])
        meta_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        story_content.append(meta_table)
        story_content.append(Spacer(1, 5 * mm))

        # ── Acceptance Criteria Legend ───────────────────────────────────────
        story_content.append(Paragraph("ACCEPTANCE CRITERIA LEGEND", h2))
        for ac in ac_legend:
            try:
                r = int(ac["color"][1:3], 16) / 255
                g = int(ac["color"][3:5], 16) / 255
                b = int(ac["color"][5:7], 16) / 255
                chip_color = colors.Color(r, g, b)
            except Exception:
                chip_color = colors.blue

            ac_text = f'<font color="#{ac["color"][1:]}">[{ac["id"]}]</font>  {ac["text"]}'
            story_content.append(Paragraph(ac_text, small))
        story_content.append(Spacer(1, 5 * mm))

        # ── Active Filters ───────────────────────────────────────────────────
        story_content.append(Paragraph("ACTIVE FILTERS", h2))
        filter_lines = []
        filter_lines.append(f"Criterion: {active_filters.get('criterion') or 'All'}")
        filter_lines.append(f"Type: {active_filters.get('type') or 'All'}")
        filter_lines.append(f"Status: {active_filters.get('status') or 'All'}")
        if active_filters.get("search"):
            filter_lines.append(f"Search: {active_filters['search']}")
        for line in filter_lines:
            story_content.append(Paragraph(line, small))
        story_content.append(Spacer(1, 5 * mm))

        # ── Matching Tests ───────────────────────────────────────────────────
        story_content.append(Paragraph(f"MATCHING TESTS: {len(tests)}", h2))
        story_content.append(Spacer(1, 2 * mm))

        # Table header
        table_header = [["Test Name", "Type", "Criteria", "Result"]]
        table_data = table_header.copy()

        for t in tests:
            name = t.get("test_name") or t.get("test_id") or "—"
            t_type = (t.get("scope") or t.get("test_type") or t.get("type") or "unit").capitalize()
            criteria_list = t.get("criteria") or []
            criteria_str = " ".join(criteria_list) if criteria_list else "—"
            status_str = (t.get("status") or "generated").upper()
            # Truncate long names
            if len(name) > 55:
                name = name[:52] + "..."
            table_data.append([name, t_type, criteria_str, status_str])

        col_widths = [90 * mm, 22 * mm, 28 * mm, 22 * mm]
        test_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        test_table.setStyle(TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            # Data rows
            ("FONTSIZE", (0, 1), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            # Color code results
        ]))

        # Color PASS/FAIL cells
        for row_idx, t in enumerate(tests, start=1):
            status_str = (t.get("status") or "generated").upper()
            if status_str == "PASSED":
                test_table.setStyle(TableStyle([
                    ("TEXTCOLOR", (3, row_idx), (3, row_idx), colors.HexColor("#16a34a")),
                    ("FONTNAME", (3, row_idx), (3, row_idx), "Helvetica-Bold"),
                ]))
            elif status_str in ("FAILED", "NEEDS_HUMAN_REVIEW"):
                test_table.setStyle(TableStyle([
                    ("TEXTCOLOR", (3, row_idx), (3, row_idx), colors.HexColor("#dc2626")),
                    ("FONTNAME", (3, row_idx), (3, row_idx), "Helvetica-Bold"),
                ]))

        story_content.append(test_table)
        story_content.append(Spacer(1, 5 * mm))

        # ── Summary ──────────────────────────────────────────────────────────
        passed_count = sum(1 for t in tests if (t.get("status") or "").lower() == "passed")
        failed_count = sum(1 for t in tests if (t.get("status") or "").lower() in ("failed", "needs_human_review"))

        summary_data = [
            ["Matching tests:", str(len(tests))],
            ["Passed:", str(passed_count)],
            ["Failed:", str(failed_count)],
        ]
        summary_table = Table(summary_data, colWidths=[40 * mm, 30 * mm])
        summary_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        story_content.append(Paragraph("SUMMARY", h2))
        story_content.append(summary_table)

        doc.build(story_content)
        return output_path

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_keyword_map(ac_legend: list[dict]) -> dict[str, list[str]]:
        """
        Build a keyword -> AC ID map from the AC legend.
        Extracts significant nouns/phrases from each AC text so edge case tests
        with similar language can be matched.
        """
        # Common stop words to skip
        stop = {
            "the", "a", "an", "and", "or", "if", "is", "are", "must", "be",
            "to", "of", "in", "for", "that", "this", "with", "at", "by",
            "from", "as", "it", "its", "on", "can", "after", "before",
            "has", "have", "not", "any", "each", "no", "all", "more",
            "than", "when", "will", "should", "only", "their", "they",
        }
        keyword_map: dict[str, list[str]] = {}
        for ac in ac_legend:
            words = re.findall(r"\b[a-z]+(?:\s+[a-z]+)?\b", ac["text"].lower())
            keywords = []
            for w in words:
                parts = w.split()
                # Include multi-word phrases and single meaningful words (4+ chars)
                if len(parts) > 1:
                    keywords.append(w)
                elif len(w) >= 4 and w not in stop:
                    keywords.append(w)
            keyword_map[ac["id"]] = keywords
        return keyword_map

    @staticmethod
    def _load_test_plan(story) -> dict:
        if not story.test_plan:
            return {"tests": []}
        try:
            data = json.loads(story.test_plan)
            return data if isinstance(data, dict) else {"tests": []}
        except (json.JSONDecodeError, TypeError):
            return {"tests": []}
