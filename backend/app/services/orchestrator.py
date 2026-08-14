import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.backlog import Feature, UserStory, Task
from app.models.execution import ExecutionRun, PullRequest
from app.models.project import Project
from app.services.claude_runner import ClaudeRunner, ClaudeResult
from app.services.crypto import decrypt_value
from app.services.github_service import GitHubService
from app.services.prompt_builder import PromptBuilder
from app.services.repository_intelligence import RepositoryIntelligence
from app.services.test_intelligence import TestIntelligence, TestIntelligenceError
from app.services.test_runner import TestRunnerService
from app.services.websocket_manager import manager as ws_manager
from app.config import settings

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        project_id: str,
        db: AsyncSession,
        skip_tests: bool = False,
        story_id: str | None = None,
    ):
        self.project_id = project_id
        self.db = db
        self.skip_tests = skip_tests
        self.story_id = story_id
        self.execution_run: ExecutionRun | None = None
        self._paused = False
        self._cancelled = False
        self._current_runner: ClaudeRunner | None = None
        self.prompt_builder = PromptBuilder()
        self._current_branch: str | None = None
        self._current_scope_id: str | None = None

    async def create_run(self) -> ExecutionRun:
        total = await self._count_pending_tasks()
        self.execution_run = ExecutionRun(
            project_id=self.project_id,
            status="running",
            total_tasks=total,
        )
        self.db.add(self.execution_run)
        await self.db.commit()
        await self.db.refresh(self.execution_run)
        return self.execution_run

    async def execute(self):
        logger.info(f"Orchestrator.execute() started for project {self.project_id}")

        project = await self.db.get(Project, self.project_id)
        if not project:
            logger.error(f"Project {self.project_id} not found")
            await self._broadcast("error", {"message": "Project not found"})
            return

        logger.info(f"Project loaded: {project.name}")

        if not self.execution_run:
            result = await self.db.execute(
                select(ExecutionRun)
                .where(ExecutionRun.project_id == self.project_id, ExecutionRun.status == "running")
                .order_by(ExecutionRun.started_at.desc())
                .limit(1)
            )
            self.execution_run = result.scalar_one_or_none()
            if not self.execution_run:
                logger.info("No existing running execution run found, creating new one")
                await self.create_run()
            else:
                logger.info(f"Resuming execution run {self.execution_run.id}")

        # Setup GitHub if configured
        github = None
        if project.github_pat_encrypted and project.github_repo_url:
            try:
                pat = decrypt_value(project.github_pat_encrypted)
                github = GitHubService(pat)
                logger.info("GitHub service initialized")
            except Exception as e:
                logger.warning(f"GitHub setup failed: {e}")
                await self._broadcast("claude_output", {"message": f"GitHub not available: {e}. Running code generation only."})

        # Setup workspace — clone repo if needed
        workspace = project.workspace_path
        if not workspace:
            import tempfile
            workspace = tempfile.mkdtemp(prefix="codegen_hub_")
            project.workspace_path = workspace
            await self.db.commit()
            logger.info(f"Created temp workspace: {workspace}")

        if github and not project.is_repo_cloned:
            try:
                await self._broadcast("claude_output", {"message": f"Cloning {project.github_repo_url}..."})
                clone_path = await github.clone_repo(project.github_repo_url, workspace)
                workspace = clone_path
                project.workspace_path = clone_path
                project.is_repo_cloned = True
                await self.db.commit()
                logger.info(f"Cloned repo to {clone_path}")
                await self._broadcast("claude_output", {"message": f"Repo cloned to {clone_path}"})
            except Exception as e:
                logger.warning(f"Clone failed: {e}")
                await self._broadcast("claude_output", {"message": f"Clone failed: {e}. Generating code in workspace without repo."})
        elif github and project.is_repo_cloned:
            # Pull latest from remote before starting
            try:
                github.pull_latest(workspace)
                logger.info("Pulled latest from remote")
                await self._broadcast("claude_output", {"message": "Pulled latest changes from remote"})
            except Exception as e:
                logger.warning(f"Pull failed (continuing with local state): {e}")
        else:
            logger.info(f"Using workspace: {workspace}")

        self._workspace = workspace  # stored so _create_pr can reference it
        await self._broadcast("claude_output", {"message": f"Workspace: {workspace}"})

        # Ensure CI workflow exists in the repo
        from app.services.ci_generator import ensure_ci_workflow
        if ensure_ci_workflow(workspace):
            await self._broadcast("claude_output", {"message": "Created .github/workflows/ci.yml"})
            if github and self._current_branch:
                try:
                    if github.has_changes(workspace):
                        github.commit_and_push(workspace, "ci: add GitHub Actions workflow", self._current_branch or "main")
                except Exception:
                    pass

        tasks = await self._get_ordered_tasks()
        logger.info(f"Found {len(tasks)} pending tasks")

        if not tasks:
            logger.info("No pending tasks found — completing run")
            await self._broadcast("claude_output", {"message": "No pending tasks to process."})
            await self._complete_run()
            return

        task_count = len(tasks)
        await self._broadcast("claude_output", {
            "message": f"Starting execution: {task_count} tasks in selected user story"
        })

        # Initialise TestIntelligence once per run
        test_intelligence = TestIntelligence(
            workspace_path=workspace,
            max_budget_usd=project.claude_max_budget_usd,
        )

        story_stopped = False  # set when story needs human review
        completed_stories = set()

        for task_data in tasks:
            if self._paused or self._cancelled or story_stopped:
                break

            task, user_story, feature = task_data

            # Approval gate (Day 2 + Day 3)
            if user_story.requirement_analysis_status != "approved":
                await self._broadcast("error", {
                    "message": (
                        "Execution blocked: Requirement Intelligence is not approved "
                        f"for '{user_story.title}'."
                    ),
                })
                break

            if user_story.implementation_plan_status != "approved":
                await self._broadcast("error", {
                    "message": (
                        "Execution blocked: Implementation Plan is not approved "
                        f"for '{user_story.title}'."
                    ),
                })
                break

            # Dependency gate (Day 2)
            dependencies_ok, reason = self._dependency_state(task, user_story)
            if not dependencies_ok:
                task.status = "blocked"
                task.error_message = reason
                if self.execution_run:
                    self.execution_run.failed_tasks += 1
                await self.db.commit()
                await self._broadcast_task_status(task.id, "blocked", task.title)
                await self._broadcast("claude_output", {"message": f"Blocked: {task.title}. {reason}"})
                continue

            requirement = self._load_json_object(user_story.requirement_analysis)
            plan = self._load_json_object(user_story.implementation_plan)

            # ── Build task code ───────────────────────────────────────────────
            await self._process_task(task, user_story, feature, project, github, workspace)

            if task.status not in {"completed", "failed"}:
                # Partial / retry handled inside _process_task
                continue

            # ── Day 3: Task-level unit tests ──────────────────────────────────
            if not self.skip_tests and task.status == "completed":
                user_story.test_status = "generating"
                user_story.test_updated_at = datetime.utcnow()
                await self.db.commit()

                unit_manifest: dict = {}
                try:
                    await self._broadcast("test_generation_started", {
                        "task_id": task.id,
                        "test_type": "unit",
                    })
                    await self._broadcast("claude_output", {
                        "message": f"Generating requirement-aware unit tests for: {task.title}"
                    })
                    unit_manifest = await test_intelligence.generate_task_tests(
                        feature, user_story, task, requirement, plan
                    )
                    # Merge into story test_plan
                    self._merge_test_plan(user_story, unit_manifest.get("tests", []))
                    await self.db.commit()

                    n_tests = len(unit_manifest.get("tests", []))
                    n_files = len(unit_manifest.get("files", []))
                    files_str = ", ".join(unit_manifest.get("files", [])) or "none"
                    await self._broadcast("claude_output", {
                        "message": f"Generated {n_tests} unit test(s) across {n_files} file(s): {files_str}"
                    })
                except TestIntelligenceError as exc:
                    logger.warning("Unit test generation failed for %s: %s", task.title, exc)
                    await self._broadcast("claude_output", {"message": f"Test generation warning: {exc}"})

                # Run generated unit tests
                user_story.test_status = "running"
                user_story.test_updated_at = datetime.utcnow()
                await self.db.commit()

                test_runner = TestRunnerService(
                    self.project_id, self.db, workspace, project.claude_max_budget_usd
                )
                modified_files = self._get_modified_files(workspace)
                explicit_files = unit_manifest.get("files", [])
                if explicit_files:
                    await self._broadcast("claude_output", {
                        "message": f"Running {len(explicit_files)} unit test file(s)..."
                    })

                unit_result = await test_runner.run_unit_tests(
                    task,
                    self.execution_run.id if self.execution_run else None,
                    modified_files,
                    explicit_files=explicit_files or None,
                )

                # Repair loop (max 3)
                if not unit_result.passed:
                    user_story.test_status = "repairing"
                    user_story.test_updated_at = datetime.utcnow()
                    await self.db.commit()

                    failing_tests = unit_manifest.get("tests", [])
                    unit_result = await test_runner.fix_with_requirement_context(
                        task=task,
                        user_story=user_story,
                        feature=feature,
                        execution_run_id=self.execution_run.id if self.execution_run else None,
                        test_result=unit_result,
                        requirement_analysis=requirement,
                        implementation_plan=plan,
                        failing_tests=failing_tests,
                        modified_files=modified_files,
                        explicit_files=explicit_files or None,
                    )

                if not unit_result.passed:
                    # Mark story needs human review and stop story execution
                    user_story.test_status = "needs_human_review"
                    user_story.test_summary = (
                        f"Task '{task.title}' unit gate failed after "
                        f"{TestRunnerService.__init__.__doc__ or 3} repair attempts."
                    )
                    user_story.test_updated_at = datetime.utcnow()
                    await self.db.commit()
                    await self._broadcast("needs_human_review", {
                        "story_id": user_story.id,
                        "task_id": task.id,
                        "reason": f"Unit tests failed after max repair attempts for: {task.title}",
                    })
                    await self._broadcast("claude_output", {
                        "message": f"Story stopped: unit gate failed for '{task.title}' after 3 repairs. Needs Human Review.",
                    })
                    story_stopped = True
                    break
                else:
                    user_story.test_status = "running"
                    user_story.test_updated_at = datetime.utcnow()
                    await self.db.commit()

            # ── Story boundary: all tasks done ────────────────────────────────
            if task.status == "completed" and user_story.id not in completed_stories:
                story_done = all(t.status == "completed" for t in user_story.tasks)
                if story_done:
                    completed_stories.add(user_story.id)
                    user_story.status = "completed"
                    await self.db.commit()

                    feature_done = all(
                        t.status == "completed"
                        for s in feature.user_stories
                        for t in s.tasks
                    )
                    if feature_done:
                        feature.status = "completed"
                        await self.db.commit()

                    # Day 3: Integration/System/Regression quality gate
                    if not self.skip_tests:
                        await self._run_story_quality_gate(
                            user_story, feature, project, workspace, test_intelligence
                        )

            # Create PR at scope boundaries
            if github and task.status == "completed":
                await self._maybe_create_scope_pr(project, github, task, user_story, feature)

        if not self._paused:
            await self._complete_run()

    async def pause(self):
        self._paused = True
        if self._current_runner:
            await self._current_runner.cancel()
        if self.execution_run:
            self.execution_run.status = "paused"
            await self.db.commit()
        await self._broadcast("execution_status_change", {"status": "paused"})
        await self._broadcast("claude_output", {"message": "Execution paused"})

    async def cancel(self):
        self._cancelled = True
        if self._current_runner:
            await self._current_runner.cancel()

    async def _process_task(
        self,
        task: Task,
        user_story: UserStory,
        feature: Feature,
        project: Project,
        github: GitHubService | None,
        workspace: str,
    ):
        task.status = "in_progress"
        if self.execution_run:
            self.execution_run.current_task_id = task.id
        await self.db.commit()

        await self._broadcast_task_status(task.id, "in_progress", task.title)
        await self._broadcast("claude_output", {"message": f"Processing: {task.title}"})

        # Branch management — only switch branch at scope boundaries
        if github and workspace:
            branch_name = self._get_branch_name(task, user_story, feature, project.pr_strategy)
            scope_id = self._get_scope_id(task, user_story, feature, project.pr_strategy)

            if scope_id != self._current_scope_id:
                try:
                    github.create_branch(workspace, branch_name)
                    self._current_branch = branch_name
                    self._current_scope_id = scope_id
                    await self._broadcast("claude_output", {"message": f"On branch: {branch_name}"})
                except Exception as e:
                    logger.warning(f"Branch creation failed: {e}")
                    await self._broadcast("claude_output", {"message": f"Branch creation skipped: {e}"})

        # Build prompt with Day 2 requirement + plan context + data model
        requirement = self._load_json_object(user_story.requirement_analysis)
        plan = self._load_json_object(user_story.implementation_plan)
        data_model = self._load_json_object(getattr(user_story, "data_model", "") or "")

        relevant_paths = []
        for item in plan.get("relevant_files", []):
            path = item.get("path")
            if path and path not in relevant_paths:
                relevant_paths.append(path)
        for item in plan.get("planned_changes", []):
            path = item.get("path")
            if path and path not in relevant_paths:
                relevant_paths.append(path)

        repo_context = ""
        if relevant_paths:
            repo_context = (
                "Repository Intelligence identified these relevant paths. "
                "Read only what this task needs:\n"
                + "\n".join(f"- {path}" for path in relevant_paths[:15])
            )

        prompt = self.prompt_builder.build_task_prompt(
            task,
            user_story,
            feature,
            repo_context=repo_context,
            requirement_analysis=requirement if requirement else None,
            implementation_plan=plan if plan else None,
            data_model=data_model if data_model and data_model.get("entities") else None,
        )
        runner = ClaudeRunner(workspace or ".", project.claude_max_budget_usd)
        self._current_runner = runner

        await self._broadcast("claude_output", {"message": f"Invoking Claude Code CLI for: {task.title}"})
        result = await runner.execute(prompt)

        if result.success:
            task.claude_session_id = result.session_id
            await self._broadcast("claude_output", {"message": f"Code generated: {task.title}"})

            # CODE IS DONE — mark completed immediately.
            # Day 3 outer loop handles all test generation, execution and repair.
            # NOTE: completed_tasks counter is incremented here for the progress bar.
            # If tests subsequently fail, the orchestrator stops the story (needs_human_review)
            # but does not decrement — the task's code was genuinely built.
            modified_files = self._get_modified_files(workspace)

            task.status = "completed"
            task.completed_at = datetime.utcnow()
            if self.execution_run:
                self.execution_run.completed_tasks += 1
            await self._broadcast_task_status(task.id, "completed", task.title)

            # Commit and push when task code is done
            if task.status == "completed":
                if github and workspace and self._current_branch:
                    try:
                        if github.has_changes(workspace):
                            github.commit_and_push(workspace, f"feat: {task.title}", self._current_branch)
                            await self._broadcast("claude_output", {"message": f"Pushed changes to {self._current_branch}"})
                    except Exception as e:
                        logger.warning(f"Git push failed: {e}")
                        await self._broadcast("claude_output", {"message": f"Git push skipped: {e}"})

                # Day 2: refresh repository metadata after task
                try:
                    repository = RepositoryIntelligence(
                        project=project,
                        db=self.db,
                        workspace_path=workspace,
                    )
                    await repository.refresh_after_task(modified_files)
                except Exception as exc:
                    logger.warning("Repository metadata refresh failed: %s", exc)

        elif result.is_partial:
            await self._broadcast("claude_output", {"message": f"Partial result for: {task.title}. Retrying..."})
            if github and workspace and self._current_branch:
                try:
                    if github.has_changes(workspace):
                        github.commit_and_push(workspace, f"wip: {task.title} (partial)", self._current_branch)
                except Exception:
                    pass
            await self._retry_task(task, result, workspace, project)

        else:
            await self._broadcast("claude_output", {"message": f"Failed: {task.title} - {result.error[:200]}"})
            await self._handle_failure(task, result)

        await self.db.commit()
        self._current_runner = None

    async def _retry_task(self, task, result, workspace, project):
        if task.retry_count >= settings.claude_max_retries:
            await self._handle_failure(task, result)
            return

        task.retry_count += 1
        await self._broadcast("claude_output", {"message": f"Retry {task.retry_count}/{settings.claude_max_retries} for: {task.title}"})

        modified = self._get_modified_files(workspace) if workspace else []
        prompt = self.prompt_builder.build_continuation_prompt(task, result.output, modified)

        runner = ClaudeRunner(workspace or ".", project.claude_max_budget_usd)
        retry_result = await runner.execute(prompt)

        if retry_result.success:
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            if self.execution_run:
                self.execution_run.completed_tasks += 1
            await self._broadcast_task_status(task.id, "completed", task.title)
        else:
            await self._handle_failure(task, retry_result)

    async def _handle_failure(self, task: Task, result: ClaudeResult):
        task.retry_count += 1
        if task.retry_count >= settings.claude_max_retries:
            task.status = "failed"
            task.error_message = result.error[:2000]
            if self.execution_run:
                self.execution_run.failed_tasks += 1
            await self._broadcast_task_status(task.id, "failed", task.title)
        else:
            task.status = "pending"
            await self._broadcast_task_status(task.id, "retry", task.title)

    async def _maybe_create_scope_pr(self, project, github, task, user_story, feature):
        pr_strategy = project.pr_strategy

        if pr_strategy == "per_task":
            await self._create_pr(project, github, task, user_story, feature)
            return

        if pr_strategy == "per_story":
            all_done = all(t.status == "completed" for t in user_story.tasks)
            if all_done:
                await self._create_pr(project, github, task, user_story, feature)

        elif pr_strategy == "per_feature":
            all_done = all(
                t.status == "completed"
                for s in feature.user_stories
                for t in s.tasks
            )
            if all_done:
                await self._create_pr(project, github, task, user_story, feature)

    async def _create_pr(self, project, github, task, user_story, feature):
        branch = self._current_branch
        if not branch:
            return

        try:
            repo_info = await github.validate_repo(project.github_repo_url)
            base = repo_info.get("default_branch", "main")

            if project.pr_strategy == "per_task":
                title = f"feat: {task.title}"
                body = f"## Task\n{task.title}\n\n## User Story\n{user_story.title}\n\n## Feature\n{feature.title}"
                scope_type = "task"
                scope_id = task.id
            elif project.pr_strategy == "per_story":
                title = f"feat: {user_story.title}"
                body = f"## User Story\n{user_story.title}\n\n## Feature\n{feature.title}\n\n## Tasks\n" + "\n".join(f"- {t.title}" for t in user_story.tasks)
                scope_type = "story"
                scope_id = user_story.id
            else:
                title = f"feat: {feature.title}"
                body = f"## Feature\n{feature.title}\n\n## Stories\n" + "\n".join(f"- {s.title}" for s in feature.user_stories)
                scope_type = "feature"
                scope_id = feature.id

            # Attach test report to PR body
            test_runner = TestRunnerService(
                self.project_id, self.db, getattr(self, '_workspace', '.'),
                project.claude_max_budget_usd,
            )
            try:
                report = await test_runner.generate_test_report(
                    self.execution_run.id if self.execution_run else "",
                    scope_type, scope_id,
                )
                body += f"\n\n{report.report_summary}"
            except Exception as e:
                logger.warning(f"Test report generation failed: {e}")

            body += "\n\n---\n*Auto-generated by CodeGen Hub*"

            pr_data = await github.create_pull_request(
                project.github_repo_url, branch, base, title, body
            )
            pr = PullRequest(
                project_id=project.id,
                execution_run_id=self.execution_run.id if self.execution_run else None,
                github_pr_number=pr_data["number"],
                github_pr_url=pr_data["url"],
                branch_name=branch,
                title=title,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            self.db.add(pr)
            await self.db.commit()

            await self._broadcast("pr_created", {
                "pr_url": pr_data["url"], "pr_number": pr_data["number"], "title": title,
            })
        except Exception as e:
            logger.error(f"PR creation failed: {e}")
            await self._broadcast("claude_output", {"message": f"PR creation failed: {e}"})

    async def _complete_run(self):
        if self.execution_run:
            self.execution_run.status = "completed"
            self.execution_run.completed_at = datetime.utcnow()
            await self.db.commit()
        await self._broadcast("execution_complete", {"status": "completed"})

    async def _broadcast_task_status(self, task_id: str, status: str, title: str):
        payload = {
            "task_id": task_id,
            "status": status,
            "title": title,
        }
        if self.execution_run:
            payload["completed_tasks"] = self.execution_run.completed_tasks
            payload["failed_tasks"] = self.execution_run.failed_tasks
            payload["total_tasks"] = self.execution_run.total_tasks
        await self._broadcast("task_status_change", payload)

    async def _broadcast(self, event_type: str, payload: dict):
        await ws_manager.broadcast(self.project_id, {"type": event_type, "payload": payload})

    @staticmethod
    def _load_json_object(value: str) -> dict:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    async def _get_ordered_tasks(self) -> list[tuple[Task, UserStory, Feature]]:
        result = await self.db.execute(
            select(Feature)
            .where(Feature.project_id == self.project_id)
            .options(
                selectinload(Feature.user_stories).selectinload(UserStory.tasks)
            )
            .order_by(Feature.order)
        )
        features = result.scalars().all()

        ordered = []
        for feature in features:
            for story in sorted(feature.user_stories, key=lambda item: item.order):
                # Day 3 / Day 2 correction: when story_id filter is set, process ONLY that story
                if self.story_id and story.id != self.story_id:
                    continue

                plan = self._load_json_object(story.implementation_plan)
                task_plan = plan.get("task_plan", [])

                # Build execution_order map from approved plan
                order_map = {
                    item.get("task_id"): item.get("execution_order", 999999)
                    for item in task_plan
                }

                # Sort ALL story tasks by approved execution_order (never hard-code a count)
                story_tasks = sorted(
                    story.tasks,
                    key=lambda task: (
                        order_map.get(task.id, 999999),
                        task.order,
                    ),
                )

                # Validate plan covers every imported task exactly once (warn, don't block)
                if task_plan:
                    plan_ids = {item.get("task_id") for item in task_plan}
                    imported_ids = {t.id for t in story.tasks}
                    missing = imported_ids - plan_ids
                    extra = plan_ids - imported_ids
                    if missing:
                        logger.warning(
                            "Plan missing task IDs %s for story '%s' — will still execute them last",
                            missing, story.title,
                        )
                    if extra:
                        logger.warning(
                            "Plan references unknown task IDs %s for story '%s'",
                            extra, story.title,
                        )

                for task in story_tasks:
                    if task.status in {"pending", "in_progress"}:
                        ordered.append((task, story, feature))
        return ordered

    def _dependency_state(
        self,
        task: Task,
        story: UserStory,
    ) -> tuple[bool, str]:
        plan = self._load_json_object(story.implementation_plan)
        entry = next(
            (
                item
                for item in plan.get("task_plan", [])
                if item.get("task_id") == task.id
            ),
            None,
        )
        if not entry:
            return True, ""

        dependencies = entry.get("depends_on", [])
        if not dependencies:
            return True, ""

        by_id = {item.id: item for item in story.tasks}
        for dependency_id in dependencies:
            dependency = by_id.get(dependency_id)
            if not dependency:
                return False, f"Unknown dependency {dependency_id}"
            if dependency.status in {"failed", "blocked"}:
                return False, f"Dependency failed: {dependency.title}"
            if dependency.status != "completed":
                return False, f"Dependency not completed: {dependency.title}"
        return True, ""

    async def _count_pending_tasks(self) -> int:
        tasks = await self._get_ordered_tasks()
        return len(tasks)

    @staticmethod
    def _get_branch_name(task, user_story, feature, pr_strategy) -> str:
        def slugify(text: str) -> str:
            return text.lower().replace(" ", "-")[:40]

        if pr_strategy == "per_task":
            return f"codegen/task/{slugify(task.title)}"
        elif pr_strategy == "per_story":
            return f"codegen/story/{slugify(user_story.title)}"
        else:
            return f"codegen/feature/{slugify(feature.title)}"

    @staticmethod
    def _get_scope_id(task, user_story, feature, pr_strategy) -> str:
        if pr_strategy == "per_task":
            return task.id
        elif pr_strategy == "per_story":
            return user_story.id
        else:
            return feature.id

    def _merge_test_plan(self, user_story: UserStory, new_tests: list[dict]):
        """Merge new test entries into the story's test_plan JSON, deduplicating by test_id."""
        existing: dict = {}
        if user_story.test_plan:
            try:
                existing = json.loads(user_story.test_plan)
            except json.JSONDecodeError:
                existing = {}
        tests = existing.get("tests", [])
        existing_ids = {t.get("test_id") for t in tests}
        for entry in new_tests:
            if entry.get("test_id") not in existing_ids:
                tests.append(entry)
                existing_ids.add(entry.get("test_id"))
            else:
                # Update status in existing entry
                for t in tests:
                    if t.get("test_id") == entry.get("test_id"):
                        t.update(entry)
                        break
        existing["tests"] = tests
        user_story.test_plan = json.dumps(existing)
        user_story.test_updated_at = datetime.utcnow()

    async def _run_story_quality_gate(
        self,
        user_story: UserStory,
        feature: Feature,
        project,
        workspace: str,
        test_intelligence: "TestIntelligence",
    ):
        requirement = self._load_json_object(user_story.requirement_analysis)
        plan = self._load_json_object(user_story.implementation_plan)

        user_story.test_status = "generating"
        user_story.test_updated_at = datetime.utcnow()
        await self.db.commit()

        story_manifest: dict = {}
        try:
            await self._broadcast("test_generation_started", {
                "story_id": user_story.id,
                "test_type": "quality",
            })
            story_manifest = await test_intelligence.generate_story_tests(
                feature, user_story, requirement, plan
            )
            self._merge_test_plan(user_story, story_manifest.get("tests", []))
            await self.db.commit()
        except TestIntelligenceError as exc:
            logger.warning("Story test generation failed for '%s': %s", user_story.title, exc)
            await self._broadcast("claude_output", {
                "message": f"Story test generation warning: {exc}",
            })

        user_story.test_status = "running"
        user_story.test_updated_at = datetime.utcnow()
        await self.db.commit()

        test_runner = TestRunnerService(
            self.project_id, self.db, workspace, project.claude_max_budget_usd
        )

        story_result = await test_runner.run_story_quality_gate(
            user_story=user_story,
            feature=feature,
            execution_run_id=self.execution_run.id if self.execution_run else None,
            requirement_analysis=requirement,
            implementation_plan=plan,
            generated_files=story_manifest.get("files", []),
            include_existing_regression=True,
        )

        _max_story_repairs = 3
        # Repair loop for story quality gate (max 3)
        repair_attempt = 0
        while not story_result.passed and repair_attempt < _max_story_repairs:
            repair_attempt += 1
            user_story.test_status = "repairing"
            user_story.test_updated_at = datetime.utcnow()
            await self.db.commit()

            await self._broadcast("repair_started", {
                "story_id": user_story.id,
                "attempt": repair_attempt,
                "stage": "quality",
            })

            # Use first incomplete task as proxy for repair context
            first_task = user_story.tasks[0] if user_story.tasks else None
            if first_task:
                repair_prompt = self.prompt_builder.build_test_repair_prompt(
                    task=first_task,
                    user_story=user_story,
                    feature=feature,
                    requirement_analysis=requirement,
                    implementation_plan=plan,
                    failing_tests=story_manifest.get("tests", []),
                    test_output=story_result.raw_output,
                    attempt=repair_attempt,
                )
                runner = ClaudeRunner(workspace, project.claude_max_budget_usd)
                await runner.execute(repair_prompt)

            story_result = await test_runner.run_story_quality_gate(
                user_story=user_story,
                feature=feature,
                execution_run_id=self.execution_run.id if self.execution_run else None,
                requirement_analysis=requirement,
                implementation_plan=plan,
                generated_files=story_manifest.get("files", []),
                include_existing_regression=True,
            )

            await self._broadcast("repair_result", {
                "story_id": user_story.id,
                "attempt": repair_attempt,
                "passed": story_result.passed,
            })

            if story_result.passed:
                break

        if story_result.passed:
            user_story.test_status = "passed"
            user_story.test_summary = (
                f"Quality gate passed: {story_result.passed_tests}/{story_result.total_tests} tests."
            )
            await self._broadcast("story_quality_gate", {
                "story_id": user_story.id,
                "status": "passed",
            })
        else:
            user_story.test_status = "needs_human_review"
            user_story.test_summary = (
                f"Quality gate failed after {repair_attempt} repairs. "
                f"{story_result.failed_tests} tests still failing."
            )
            await self._broadcast("needs_human_review", {
                "story_id": user_story.id,
                "stage": "quality",
                "reason": "Story quality gate failed after max repairs.",
            })

        user_story.test_updated_at = datetime.utcnow()
        await self.db.commit()

    @staticmethod
    def _get_modified_files(workspace: str) -> list[str]:
        from git import Repo
        try:
            repo = Repo(workspace)
            return [item.a_path for item in repo.index.diff(None)] + repo.untracked_files
        except Exception:
            return []
