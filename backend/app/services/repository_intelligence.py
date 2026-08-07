import hashlib
import re
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, RepositoryFile


class RepositoryIntelligence:
    """
    Persistent, metadata-only repository intelligence.
    Stores only metadata:
    relative path, category, symbols, imports, SHA-256 and size.
    Complete source-code contents are never persisted in repository_files.
    """

    SKIP_DIRS = {
        ".git", ".venv", "venv", "node_modules", "__pycache__",
        "dist", "build", "target", "coverage", ".idea", ".vscode",
        ".pytest_cache", ".mypy_cache",
    }

    ALLOWED_EXTENSIONS = {
        ".py", ".java", ".kt", ".js", ".jsx", ".ts", ".tsx",
        ".vue", ".go", ".rs", ".cs", ".html", ".css", ".scss",
        ".sql", ".json", ".yaml", ".yml", ".toml", ".xml",
        ".gradle", ".md",
    }

    SOURCE_EXTENSIONS = {
        ".py", ".java", ".kt", ".js", ".jsx", ".ts", ".tsx",
        ".vue", ".go", ".rs", ".cs",
    }

    STOP_WORDS = {
        "the", "and", "for", "with", "that", "this", "from",
        "user", "story", "want", "able", "should", "must",
        "create", "implement", "add", "into", "when", "then",
        "have", "has",
    }

    MAX_SCAN_BYTES = 80_000

    def __init__(
        self,
        project: Project,
        db: AsyncSession,
        workspace_path: str,
    ):
        self.project = project
        self.db = db
        self.workspace = Path(workspace_path).resolve()

    async def ensure_current(self) -> None:
        """Build once, then refresh incrementally."""
        existing_count = await self._count_rows()
        if existing_count == 0:
            await self._full_index()
            return

        current_commit = self._git_head()
        if current_commit:
            changed: set[str] = set()
            if (
                self.project.repository_index_commit
                and self.project.repository_index_commit != current_commit
            ):
                changed.update(
                    self._git_changed_between(
                        self.project.repository_index_commit,
                        current_commit,
                    )
                )
            # Include uncommitted/generated files too.
            changed.update(self._git_worktree_changes())
            if changed:
                await self._refresh_paths(sorted(changed))
            self.project.repository_index_commit = current_commit
        else:
            # Local non-Git workspace: hash comparison.
            await self._refresh_local_hashes()
            self.project.repository_index_commit = ""

        self.project.repository_indexed_at = datetime.utcnow()
        await self.db.commit()

    async def find_relevant(
        self,
        feature,
        story,
        requirement_analysis: dict,
        limit: int = 12,
    ) -> dict:
        await self.ensure_current()

        query_text = " ".join(
            [
                feature.title or "",
                feature.description or "",
                story.title or "",
                story.description or "",
                story.acceptance_criteria or "",
                requirement_analysis.get("summary", ""),
                " ".join(
                    requirement_analysis.get("acceptance_criteria", [])
                ),
                " ".join(
                    requirement_analysis.get("functional_rules", [])
                ),
                " ".join(
                    requirement_analysis.get("edge_cases", [])
                ),
            ]
        )

        keywords = self._keywords(query_text)

        rows = (
            await self.db.execute(
                select(RepositoryFile).where(
                    RepositoryFile.project_id == self.project.id
                )
            )
        ).scalars().all()

        ranked = []
        for row in rows:
            haystack = (
                f"{row.relative_path} {row.category} "
                f"{row.symbols_json} {row.imports_json}"
            ).lower()

            score = 0
            for keyword in keywords:
                if keyword in row.relative_path.lower():
                    score += 5
                elif keyword in haystack:
                    score += 3

            if row.category in {
                "model", "service", "api", "controller", "frontend", "test"
            }:
                score += 1

            if score > 0:
                ranked.append((score, row))

        ranked.sort(key=lambda item: item[0], reverse=True)

        candidates = [
            {
                "path": row.relative_path,
                "category": row.category,
                "symbols": self._split_lines(row.symbols_json)[:20],
                "imports": self._split_lines(row.imports_json)[:20],
                "relevance_score": score,
            }
            for score, row in ranked[:limit]
        ]

        if not candidates:
            candidates = self._architecture_candidates(rows, limit)

        return {
            "repository_empty": self._is_effectively_empty(rows),
            "indexed_file_count": len(rows),
            "source_type": "git" if self._is_git() else "local",
            "keywords": sorted(keywords)[:30],
            "candidates": candidates,
        }

    async def refresh_after_task(
        self,
        changed_files: list[str] | None = None,
    ) -> None:
        """Refresh metadata after Claude changes code."""
        if self._is_git() and changed_files:
            await self._refresh_paths(changed_files)
            self.project.repository_index_commit = self._git_head() or ""
            self.project.repository_indexed_at = datetime.utcnow()
            await self.db.commit()
            return
        # Local workspace, or Git changed-file detection unavailable.
        await self.ensure_current()

    async def _full_index(self) -> None:
        await self.db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.project_id == self.project.id
            )
        )
        for path in self._iter_indexable_files():
            metadata = self._metadata(path)
            if metadata:
                self.db.add(
                    RepositoryFile(
                        project_id=self.project.id,
                        **metadata,
                    )
                )
        self.project.repository_index_commit = self._git_head() or ""
        self.project.repository_indexed_at = datetime.utcnow()
        await self.db.commit()

    async def _refresh_paths(self, relative_paths: list[str]) -> None:
        for raw_path in relative_paths:
            normalized = raw_path.replace("\\", "/").lstrip("/")
            full_path = self.workspace / normalized

            result = await self.db.execute(
                select(RepositoryFile).where(
                    RepositoryFile.project_id == self.project.id,
                    RepositoryFile.relative_path == normalized,
                )
            )
            row = result.scalar_one_or_none()

            if (
                not full_path.exists()
                or not full_path.is_file()
                or self._should_skip(Path(normalized))
            ):
                if row:
                    await self.db.delete(row)
                continue

            metadata = self._metadata(full_path)
            if not metadata:
                continue

            if row:
                for key, value in metadata.items():
                    setattr(row, key, value)
            else:
                self.db.add(
                    RepositoryFile(
                        project_id=self.project.id,
                        **metadata,
                    )
                )
        await self.db.flush()

    async def _refresh_local_hashes(self) -> None:
        rows = (
            await self.db.execute(
                select(RepositoryFile).where(
                    RepositoryFile.project_id == self.project.id
                )
            )
        ).scalars().all()

        existing = {row.relative_path: row for row in rows}
        current_paths = set()

        for path in self._iter_indexable_files():
            relative = path.relative_to(self.workspace).as_posix()
            current_paths.add(relative)
            current_hash = self._sha256(path)
            row = existing.get(relative)
            if row and row.sha256 == current_hash:
                continue
            metadata = self._metadata(path)
            if not metadata:
                continue
            if row:
                for key, value in metadata.items():
                    setattr(row, key, value)
            else:
                self.db.add(
                    RepositoryFile(
                        project_id=self.project.id,
                        **metadata,
                    )
                )

        for relative, row in existing.items():
            if relative not in current_paths:
                await self.db.delete(row)
        await self.db.flush()

    async def _count_rows(self) -> int:
        ids = (
            await self.db.execute(
                select(RepositoryFile.id).where(
                    RepositoryFile.project_id == self.project.id
                )
            )
        ).scalars().all()
        return len(ids)

    def _iter_indexable_files(self):
        if not self.workspace.exists():
            return
        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(self.workspace)
            except ValueError:
                continue
            if self._should_skip(relative):
                continue
            yield path

    def _metadata(self, path: Path) -> dict | None:
        try:
            raw = path.read_bytes()
            text = raw[: self.MAX_SCAN_BYTES].decode("utf-8", errors="ignore")
            relative = path.relative_to(self.workspace).as_posix()
            return {
                "relative_path": relative,
                "extension": path.suffix.lower(),
                "category": self._classify(path),
                "symbols_json": "\n".join(self._symbols(text)),
                "imports_json": "\n".join(
                    self._imports(text, path.suffix.lower())
                ),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "last_indexed_at": datetime.utcnow(),
            }
        except Exception:
            return None

    def _should_skip(self, relative: Path) -> bool:
        if any(part in self.SKIP_DIRS for part in relative.parts):
            return True
        return relative.suffix.lower() not in self.ALLOWED_EXTENSIONS

    @staticmethod
    def _classify(path: Path) -> str:
        value = path.as_posix().lower()
        if "test" in value:
            return "test"
        if "service" in value:
            return "service"
        if "controller" in value:
            return "controller"
        if "/api/" in value:
            return "api"
        if "model" in value:
            return "model"
        if "component" in value or path.suffix.lower() == ".vue":
            return "frontend"
        if "config" in value:
            return "configuration"
        return "source"

    @staticmethod
    def _symbols(text: str) -> list[str]:
        patterns = [
            r"\bclass\s+([A-Za-z_]\w*)",
            r"\bdef\s+([A-Za-z_]\w*)",
            r"\bfunction\s+([A-Za-z_]\w*)",
            r"\binterface\s+([A-Za-z_]\w*)",
            r"\benum\s+([A-Za-z_]\w*)",
            r"\b(?:const|let|var)\s+([A-Za-z_]\w*)",
        ]
        result = []
        seen = set()
        for pattern in patterns:
            for name in re.findall(pattern, text):
                if name in seen:
                    continue
                seen.add(name)
                result.append(name)
                if len(result) >= 50:
                    return result
        return result

    @staticmethod
    def _imports(text: str, extension: str) -> list[str]:
        patterns = []
        if extension == ".py":
            patterns = [
                r"^\s*import\s+([A-Za-z0-9_\.]+)",
                r"^\s*from\s+([A-Za-z0-9_\.]+)\s+import",
            ]
        elif extension in {".js", ".jsx", ".ts", ".tsx", ".vue"}:
            patterns = [
                r'from\s+[\'"]([^\'"]+)[\'"]',
                r'require\([\'"]([^\'"]+)[\'"]\)',
            ]
        elif extension in {".java", ".kt"}:
            patterns = [r"^\s*import\s+([A-Za-z0-9_\.]+)"]

        result = []
        seen = set()
        for pattern in patterns:
            for value in re.findall(pattern, text, re.MULTILINE):
                if value in seen:
                    continue
                seen.add(value)
                result.append(value)
                if len(result) >= 50:
                    return result
        return result

    def _keywords(self, text: str) -> set[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
        return {word for word in words if word not in self.STOP_WORDS}

    def _architecture_candidates(
        self,
        rows: list[RepositoryFile],
        limit: int,
    ) -> list[dict]:
        preferred = (
            "readme", "requirements.txt", "pyproject.toml", "package.json",
            "pom.xml", "build.gradle", "main.py", "app.py", "config",
        )
        result = []
        for row in rows:
            if any(token in row.relative_path.lower() for token in preferred):
                result.append(
                    {
                        "path": row.relative_path,
                        "category": row.category,
                        "symbols": self._split_lines(row.symbols_json)[:20],
                        "imports": self._split_lines(row.imports_json)[:20],
                        "relevance_score": 1,
                    }
                )
                if len(result) >= limit:
                    break
        return result

    def _is_effectively_empty(self, rows: list[RepositoryFile]) -> bool:
        return not any(
            row.extension in self.SOURCE_EXTENSIONS
            for row in rows
        )

    def _is_git(self) -> bool:
        return (self.workspace / ".git").exists()

    def _git_head(self) -> str | None:
        if not self._is_git():
            return None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _git_changed_between(self, old_commit: str, new_commit: str) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", old_commit, new_commit],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return [
                    line.strip()
                    for line in result.stdout.splitlines()
                    if line.strip()
                ]
        except Exception:
            pass
        return []

    def _git_worktree_changes(self) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return []
            changed = []
            for line in result.stdout.splitlines():
                if len(line) < 4:
                    continue
                value = line[3:].strip()
                if " -> " in value:
                    value = value.split(" -> ", 1)[1]
                if value:
                    changed.append(value)
            return changed
        except Exception:
            return []

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _split_lines(value: str) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.splitlines() if item.strip()]
