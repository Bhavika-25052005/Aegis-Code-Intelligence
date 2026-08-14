"""
Code Quality Service - Day 5.
Real coverage + Claude code review + deterministic scoring + release readiness + stale detection.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_RELEASE_RULES = {
    "minimum_coverage": 70,
    "require_all_tests_passed": True,
    "require_acceptance_traceability": True,
    "max_critical_findings": 0,
    "max_high_findings": 0,
    "require_readme": True,
    "require_fresh_quality_analysis": True,
}

SEVERITY_DEDUCTIONS = {"critical": 25, "high": 15, "medium": 7, "low": 2}
VALID_SEVERITIES = set(SEVERITY_DEDUCTIONS.keys())
VALID_CATEGORIES = {"maintainability", "readability", "error_handling", "architecture_fit", "security"}

_IGNORE_DIRS = {
    ".venv", "venv", ".env", "node_modules", ".git", "dist", "build",
    "__pycache__", ".pytest_cache", ".mypy_cache", "htmlcov", ".coverage",
    ".tox", "eggs", ".eggs",
}
_IGNORE_EXTS = {".pyc", ".pyo", ".pyd"}


class CodeQualityService:

    # ── Coverage ──────────────────────────────────────────────────────────────

    async def run_coverage(self, project, story, workspace: str) -> dict:
        """Run real coverage tooling in the target workspace. Never fabricates numbers."""
        if not workspace or not Path(workspace).exists():
            return {"status": "unavailable", "reason": "Workspace not configured or missing", "tool": None}

        wp = Path(workspace)

        # Python: look for tests and pytest configuration
        has_python_tests = (
            (wp / "pytest.ini").exists()
            or (wp / "setup.cfg").exists()
            or (wp / "pyproject.toml").exists()
            or bool(list(wp.rglob("test_*.py"))[:1])
            or bool(list(wp.rglob("*_test.py"))[:1])
        )
        if has_python_tests:
            return await self._run_pytest_cov(workspace)

        # JS/TS: check package.json for vitest or jest
        pkg_json = wp / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "vitest" in all_deps or "@vitest/coverage-v8" in all_deps:
                    return await self._run_vitest_cov(workspace)
                if "jest" in all_deps:
                    return await self._run_jest_cov(workspace)
            except Exception as exc:
                logger.warning("package.json parse error: %s", exc)

        return {"status": "unavailable", "reason": "No supported coverage configuration detected", "tool": None}

    @staticmethod
    def _detect_source_dirs(workspace: str) -> list[str]:
        """Return source dirs to measure coverage for (excluding test dirs)."""
        wp = Path(workspace)
        # Common source directory names - prefer explicit source over measuring everything
        for candidate in ("backend", "app", "src", "lib", "source"):
            if (wp / candidate).is_dir():
                return [str(wp / candidate)]
        # No canonical source dir found - use workspace but exclude test dirs via omit
        return [workspace]

    async def _run_pytest_cov(self, workspace: str) -> dict:
        import asyncio
        wp = Path(workspace)
        cov_file = wp / ".aegis_cov.json"

        # If the project has its own .coveragerc, respect it - don't add conflicting flags
        coveragerc = wp / ".coveragerc"
        has_coveragerc = coveragerc.exists()

        if has_coveragerc:
            # Project controls source and omit via .coveragerc
            config_args: list[str] = [f"--cov-config={coveragerc}"]
            # Still need at least one --cov= target so pytest-cov activates
            source_dirs = self._detect_source_dirs(workspace)
            cov_args = [f"--cov={d}" for d in source_dirs]
            extra_omit: list[str] = []
        else:
            config_args = []
            source_dirs = self._detect_source_dirs(workspace)
            cov_args = [f"--cov={d}" for d in source_dirs]
            omit_globs = [
                "*/tests/*", "*/test/*", "*/test_*.py", "*_test.py",
                "*/.venv/*", "*/venv/*", "*/node_modules/*",
                "*/__pycache__/*", "*/dist/*", "*/build/*",
            ]
            extra_omit = [f"--cov-omit={','.join(omit_globs)}"]

        cmd = [
            sys.executable, "-m", "pytest",
            *cov_args,
            *config_args,
            *extra_omit,
            f"--cov-report=json:{cov_file}",
            "--no-header", "-q",
            f"--rootdir={workspace}",
        ]
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = workspace + (os.pathsep + existing if existing else "")

        try:
            loop = asyncio.get_event_loop()
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd, cwd=workspace, capture_output=True, text=True, timeout=180, env=env
                ),
            )
        except subprocess.TimeoutExpired:
            return {"status": "error", "reason": "Coverage run timed out after 180s", "tool": "pytest-cov"}
        except Exception as exc:
            return {"status": "error", "reason": f"Coverage run failed: {str(exc)[:200]}", "tool": "pytest-cov"}

        if not cov_file.exists():
            stderr = proc.stderr or ""
            if "no module named pytest_cov" in stderr.lower() or "--cov" in stderr.lower():
                return {
                    "status": "unavailable",
                    "reason": "pytest-cov not installed. Run: pip install pytest-cov",
                    "tool": "pytest-cov",
                }
            return {
                "status": "error",
                "reason": f"Coverage JSON not produced. {stderr[:200]}",
                "tool": "pytest-cov",
            }

        try:
            raw = json.loads(cov_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "error", "reason": f"Could not parse coverage JSON: {exc}", "tool": "pytest-cov"}
        finally:
            try:
                cov_file.unlink(missing_ok=True)
            except Exception:
                pass

        totals = raw.get("totals", {})

        # Branch coverage (available when --cov-branch is set or configured)
        n_branches = totals.get("num_branches")
        c_branches = totals.get("covered_branches")
        branch_pct: Optional[float] = None
        if n_branches and n_branches > 0 and c_branches is not None:
            branch_pct = round(c_branches / n_branches * 100, 1)

        # File-level: skip ignored dirs AND files with 0% coverage.
        # Also accumulate line counts to recalculate overall excluding 0% files.
        files_out = []
        kept_covered = 0
        kept_statements = 0

        for rel_path, fdata in raw.get("files", {}).items():
            parts = Path(rel_path).parts
            if any(d in parts for d in _IGNORE_DIRS):
                continue
            summary = fdata.get("summary", {})
            num_stmts = summary.get("num_statements", 0)
            covered = summary.get("covered_lines", 0)
            pct = round(summary.get("percent_covered", 0.0), 1)

            # Exclude files with statements but 0% coverage from display and overall
            if num_stmts > 0 and pct == 0.0:
                continue

            files_out.append({"path": rel_path, "coverage": pct})
            kept_covered += covered
            kept_statements += num_stmts

        files_out.sort(key=lambda x: x["coverage"])

        # Overall recalculated from non-zero files only
        overall = round(kept_covered / kept_statements * 100, 1) if kept_statements > 0 else 0.0

        return {
            "status": "available",
            "tool": "pytest-cov",
            "overall": overall,
            "statements": None,
            "functions": None,
            "branches": branch_pct,
            "files": files_out,
            "generated_at": datetime.utcnow().isoformat(),
            "workspace_fingerprint": self.workspace_fingerprint(workspace),
        }

    async def _run_vitest_cov(self, workspace: str) -> dict:
        import asyncio
        cmd = ["npx", "vitest", "run", "--coverage", "--reporter=verbose"]
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=120),
            )
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200], "tool": "vitest"}

        summary_file = Path(workspace) / "coverage" / "coverage-summary.json"
        if not summary_file.exists():
            return {"status": "unavailable", "reason": "Vitest coverage-summary.json not produced", "tool": "vitest"}

        try:
            data = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200], "tool": "vitest"}

        total = data.get("total", {})
        lines_pct = total.get("lines", {}).get("pct")
        stmts_pct = total.get("statements", {}).get("pct")
        fn_pct = total.get("functions", {}).get("pct")
        br_pct = total.get("branches", {}).get("pct")
        overall = lines_pct or stmts_pct or 0

        files_out = [
            {"path": p, "coverage": round(fd.get("lines", {}).get("pct") or 0, 1)}
            for p, fd in data.items() if p != "total"
        ]
        files_out.sort(key=lambda x: x["coverage"])

        return {
            "status": "available",
            "tool": "vitest",
            "overall": round(overall, 1),
            "lines": round(lines_pct, 1) if lines_pct is not None else None,
            "statements": round(stmts_pct, 1) if stmts_pct is not None else None,
            "functions": round(fn_pct, 1) if fn_pct is not None else None,
            "branches": round(br_pct, 1) if br_pct is not None else None,
            "files": files_out,
            "generated_at": datetime.utcnow().isoformat(),
            "workspace_fingerprint": self.workspace_fingerprint(workspace),
        }

    async def _run_jest_cov(self, workspace: str) -> dict:
        import asyncio
        cmd = ["npx", "jest", "--coverage", "--coverageReporters=json-summary", "--passWithNoTests"]
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=120),
            )
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200], "tool": "jest"}

        summary_file = Path(workspace) / "coverage" / "coverage-summary.json"
        if not summary_file.exists():
            return {"status": "unavailable", "reason": "Jest coverage-summary.json not produced", "tool": "jest"}

        try:
            data = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200], "tool": "jest"}

        total = data.get("total", {})
        lines_pct = total.get("lines", {}).get("pct")
        stmts_pct = total.get("statements", {}).get("pct")
        fn_pct = total.get("functions", {}).get("pct")
        br_pct = total.get("branches", {}).get("pct")
        overall = lines_pct or stmts_pct or 0

        return {
            "status": "available",
            "tool": "jest",
            "overall": round(overall, 1),
            "lines": round(lines_pct, 1) if lines_pct is not None else None,
            "statements": round(stmts_pct, 1) if stmts_pct is not None else None,
            "functions": round(fn_pct, 1) if fn_pct is not None else None,
            "branches": round(br_pct, 1) if br_pct is not None else None,
            "files": [],
            "generated_at": datetime.utcnow().isoformat(),
            "workspace_fingerprint": self.workspace_fingerprint(workspace),
        }

    # ── Claude Code Review ────────────────────────────────────────────────────

    async def run_code_review(self, project, story, workspace: str, coverage: dict) -> dict:
        """Read-only Claude review. Returns structured findings and scores."""
        from app.services.claude_runner import ClaudeRunner

        req = self._load_json(story.requirement_analysis)
        plan = self._load_json(story.implementation_plan)

        changed_files: list[str] = []
        for c in plan.get("planned_changes", []):
            p = c.get("path", "")
            if p and p not in changed_files:
                changed_files.append(p)
        for item in plan.get("relevant_files", []):
            p = item.get("path", "")
            if p and p not in changed_files:
                changed_files.append(p)

        cov_context = (
            f"Coverage {coverage['overall']}% (tool: {coverage['tool']})"
            if coverage.get("status") == "available"
            else f"Coverage {coverage.get('status')}: {coverage.get('reason', '')}"
        )

        files_block = "\n".join(f"- {f}" for f in changed_files[:20]) or "No files listed in plan"

        prompt = f"""You are performing a READ-ONLY code quality review for Aegis.

## Approved Requirement Contract
{json.dumps(req, indent=2)[:2000]}

## Approved Implementation Plan
Work summary: {plan.get('work_summary', 'N/A')}
Architecture notes: {json.dumps(plan.get('architecture_notes', []))[:400]}

## Files Created/Modified by This Story
{files_block}

## Completed Tasks
{json.dumps([t.title for t in story.tasks if t.status == 'completed'])[:400]}

## Test Status
{story.test_status} - {(story.test_summary or '')[:200]}

## Coverage
{cov_context}

Review ONLY these categories: maintainability, readability, error_handling, architecture_fit, security

Rules:
- Read and inspect the files listed above. Use Glob/Grep for context.
- Return findings ONLY when supported by code you actually read.
- Do NOT modify any files.
- Do NOT run tests or repair code.
- Do NOT invent line numbers.
- severity must be exactly: critical | high | medium | low
- category must be exactly: maintainability | readability | error_handling | architecture_fit | security

Also inspect the code for:
- Personal info collected: any collection, storage, or transmission of personal data (names, emails, IDs, addresses, phone numbers, etc.)
- Sensitive info generated: tokens, secrets, keys, passwords, session data, PII outputs produced by the app
- Bad code practices: hardcoded credentials, eval/exec of user input, SQL string concatenation, missing input validation, insecure defaults, dead code, god functions, magic numbers

Return strict JSON as the LAST thing in your response:
{{
  "findings": [
    {{
      "severity": "medium",
      "category": "error_handling",
      "file": "app/services/example.py",
      "line_or_area": "create_item",
      "finding": "Broad exception handling hides expected failures.",
      "recommendation": "Handle expected integrity errors separately."
    }}
  ],
  "summary": "Concise overall review summary.",
  "details": {{
    "personal_info": ["List each distinct type of personal data collected, one string per item. Empty array if none."],
    "sensitive_info": ["List each type of sensitive data generated or exposed, one string per item. Empty array if none."],
    "bad_practices": ["List each bad practice found with file/location, one string per item. Empty array if none."]
  }}
}}
"""

        budget = min(getattr(project, "claude_max_budget_usd", 2.0), 2.0)
        runner = ClaudeRunner(workspace_path=workspace, max_budget_usd=budget, allowed_tools="Read,Glob,Grep")
        result = await runner.execute(prompt)

        _empty_details = {"personal_info": [], "sensitive_info": [], "bad_practices": []}

        if not result.success:
            return {
                "status": "error",
                "findings": [],
                "scores": self.calculate_review_scores([]),
                "summary": f"Code review failed: {(result.error or '')[:200]}",
                "details": _empty_details,
            }

        parsed = self._parse_review_json(result.output or "")
        if parsed is None:
            return {
                "status": "error",
                "findings": [],
                "scores": self.calculate_review_scores([]),
                "summary": "Code review returned invalid JSON.",
                "details": _empty_details,
            }

        findings = []
        for f in parsed.get("findings", []):
            sev = str(f.get("severity", "")).lower().strip()
            cat = str(f.get("category", "")).lower().strip()
            if sev not in VALID_SEVERITIES or cat not in VALID_CATEGORIES:
                continue
            findings.append({
                "severity": sev,
                "category": cat,
                "file": str(f.get("file", ""))[:200],
                "line_or_area": str(f.get("line_or_area", ""))[:200],
                "finding": str(f.get("finding", ""))[:500],
                "recommendation": str(f.get("recommendation", ""))[:500],
            })

        raw_details = parsed.get("details", {})
        details = {
            "personal_info": [str(s)[:500] for s in raw_details.get("personal_info", []) if s],
            "sensitive_info": [str(s)[:500] for s in raw_details.get("sensitive_info", []) if s],
            "bad_practices": [str(s)[:500] for s in raw_details.get("bad_practices", []) if s],
        }

        return {
            "status": "ok",
            "findings": findings,
            "scores": self.calculate_review_scores(findings),
            "summary": str(parsed.get("summary", ""))[:1000],
            "details": details,
        }

    def _parse_review_json(self, output: str) -> Optional[dict]:
        if not output.strip():
            return None
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL | re.IGNORECASE)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except Exception:
                pass
        start, end = output.rfind("{"), output.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(output[start:end + 1])
            except Exception:
                pass
        return None

    # ── Scoring ───────────────────────────────────────────────────────────────

    def calculate_review_scores(self, findings: list[dict]) -> dict:
        """Deterministic: start 100, deduct by severity per category, min 0."""
        scores = {cat: 100 for cat in VALID_CATEGORIES}
        for f in findings:
            cat = f.get("category", "").lower()
            sev = f.get("severity", "").lower()
            if cat in scores and sev in SEVERITY_DEDUCTIONS:
                scores[cat] = max(0, scores[cat] - SEVERITY_DEDUCTIONS[sev])
        overall = round(sum(scores.values()) / len(scores), 1)
        return {**scores, "overall": overall}

    # ── Release Readiness ─────────────────────────────────────────────────────

    def calculate_release_readiness(
        self, project, story, quality_snapshot: dict, rules: Optional[dict] = None
    ) -> dict:
        """Fully deterministic. Claude does NOT decide READY/NOT READY."""
        minimum_coverage = (rules or {}).get("minimum_coverage", DEFAULT_RELEASE_RULES["minimum_coverage"])

        coverage = quality_snapshot.get("coverage", {})
        review = quality_snapshot.get("review", {})
        findings = review.get("findings", [])
        saved_fp = quality_snapshot.get("workspace_fingerprint", "")
        workspace = getattr(project, "workspace_path", "") or ""
        current_fp = self.workspace_fingerprint(workspace)
        is_stale = bool(saved_fp and saved_fp != current_fp)

        checks: list[dict] = []

        def chk(key, label, passed, blocking, msg=""):
            checks.append({"key": key, "label": label, "passed": passed, "blocking": blocking, "message": msg})

        # 1. Requirements Contract Approval
        req_ok = story.requirement_analysis_status == "approved"
        chk("requirement_approved", "Requirements Contract Approval", req_ok, True,
            "" if req_ok else "Requirement contract not approved")

        # 2. Implementation Plan Generation
        plan_ok = story.implementation_plan_status == "approved"
        chk("plan_approved", "Implementation Plan Generation", plan_ok, True,
            "" if plan_ok else "Implementation plan not approved")

        # 3. Code Coverage (>70%)
        cov_status = coverage.get("status", "unavailable")
        cov_val = coverage.get("overall")
        if cov_status == "available" and cov_val is not None:
            cov_ok = cov_val >= minimum_coverage
            chk("coverage_threshold", f"Code Coverage (>{minimum_coverage}%)", cov_ok, True,
                "" if cov_ok else f"Coverage {cov_val}% < required {minimum_coverage}%")
        else:
            chk("coverage_threshold", f"Code Coverage (>{minimum_coverage}%)", False, True,
                f"Coverage unavailable: {coverage.get('reason', 'run quality analysis')}")

        # 4. Code Review
        review_ok = review.get("status") == "ok"
        chk("code_review", "Code Review", review_ok, True,
            "" if review_ok else "Code review not completed or failed")

        # 5. No Critical Security Flaws (must be zero)
        crit = sum(1 for f in findings if f.get("severity") == "critical")
        crit_ok = crit == 0
        chk("critical_findings", "No Critical Security Flaws", crit_ok, True,
            "" if crit_ok else f"{crit} critical finding(s) found")

        # 6. Tests Passing
        gate_ok = story.test_status == "passed"
        chk("tests_passing", "Tests Passing", gate_ok, True,
            "" if gate_ok else f"Quality gate: {story.test_status}")

        # 7. Deployment Guide (README)
        readme_ok = bool(workspace and (Path(workspace) / "README.md").exists())
        chk("readme_present", "Deployment Guide (README)", readme_ok, True,
            "" if readme_ok else "README.md missing")

        # 8. GitHub Configuration
        repo_ok = bool(getattr(project, "github_repo_url", None))
        chk("repo_configured", "GitHub Configuration", repo_ok, True,
            "" if repo_ok else "No GitHub repository configured")

        blockers = [
            {"key": c["key"], "message": c["message"] or c["label"]}
            for c in checks if c["blocking"] and not c["passed"]
        ]
        warnings = [
            {"key": c["key"], "message": c["message"] or c["label"]}
            for c in checks if not c["blocking"] and not c["passed"] and c.get("message")
        ]

        return {
            "status": "ready" if not blockers else "not_ready",
            "passed_checks": sum(1 for c in checks if c["passed"]),
            "total_checks": len(checks),
            "blockers": blockers,
            "warnings": warnings,
            "checks": checks,
            "is_stale": is_stale,
        }

    # ── Workspace Fingerprint ─────────────────────────────────────────────────

    def workspace_fingerprint(self, workspace: str, relevant_files=None) -> str:
        if not workspace or not Path(workspace).exists():
            return ""
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=workspace, capture_output=True, text=True, timeout=5
            )
            if head.returncode == 0:
                dirty = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=workspace, capture_output=True, text=True, timeout=5
                ).stdout.strip()
                return hashlib.sha256(f"{head.stdout.strip()}:{dirty}".encode()).hexdigest()[:32]
        except Exception:
            pass

        # Non-git fallback: hash file mtimes
        hasher = hashlib.sha256()
        wp = Path(workspace)
        files = sorted(
            p for p in wp.rglob("*")
            if p.is_file()
            and not any(d in p.parts for d in _IGNORE_DIRS)
            and p.suffix not in _IGNORE_EXTS
        )
        for p in files[:500]:
            try:
                hasher.update(str(p.relative_to(wp)).encode())
                hasher.update(str(p.stat().st_mtime).encode())
            except Exception:
                pass
        return hasher.hexdigest()[:32]

    @staticmethod
    def _load_json(val: str) -> dict:
        try:
            return json.loads(val) if val else {}
        except Exception:
            return {}
