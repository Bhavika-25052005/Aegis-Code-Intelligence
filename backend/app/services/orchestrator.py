import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.backlog import Feature, UserStory, Task
from app.models.execution import ExecutionRun, PullRequest
from app.models.project import Project
from app.services.claude_runner import ClaudeRunner, ClaudeResult
from app.services.crypto import decrypt_value
from app.services.github_service import GitHubService
from app.services.prompt_builder import PromptBuilder
from app.services.websocket_manager import manager as ws_manager
from app.config import settings

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, project_id: str, db: AsyncSession):
        self.project_id = project_id
        self.db = db
        self.run: ExecutionRun | None = None
        self._paused = False
        self._cancelled = False
        self._current_runner: ClaudeRunner | None = None
        self.prompt_builder = PromptBuilder()

    async def create_run(self) -> ExecutionRun:
        total = await self._count_pending_tasks()
        self.run = ExecutionRun(
            project_id=self.project_id,
            status="running",
            total_tasks=total,
        )
        self.db.add(self.run)
        await self.db.commit()
        await self.db.refresh(self.run)
        return self.run

    async def run(self):
        project = await self.db.get(Project, self.project_id)
        if not project:
            logger.error(f"Project {self.project_id} not found")
            return

        pat = decrypt_value(project.github_pat_encrypted)
        github = GitHubService(pat)
        workspace = project.workspace_path

        tasks = await self._get_ordered_tasks()
        if not tasks:
            await self._complete_run()
            return

        for task_data in tasks:
            if self._paused or self._cancelled:
                break

            task, user_story, feature = task_data
            await self._process_task(task, user_story, feature, project, github, workspace)

            if self._should_create_pr(task, project.pr_strategy):
                await self._create_pr(project, github, task, user_story, feature)

        if not self._paused:
            await self._complete_run()

    async def pause(self):
        self._paused = True
        if self._current_runner:
            await self._current_runner.cancel()
        if self.run:
            self.run.status = "paused"
            await self.db.commit()

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
        github: GitHubService,
        workspace: str,
    ):
        task.status = "in_progress"
        if self.run:
            self.run.current_task_id = task.id
        await self.db.commit()

        await ws_manager.broadcast(self.project_id, {
            "type": "task_status_change",
            "payload": {"task_id": task.id, "status": "in_progress", "title": task.title},
        })

        branch_name = self._get_branch_name(task, user_story, feature, project.pr_strategy)
        github.create_branch(workspace, branch_name)

        prompt = self.prompt_builder.build_task_prompt(task, user_story, feature)

        runner = ClaudeRunner(workspace, project.claude_max_budget_usd)
        self._current_runner = runner

        result = await runner.execute(prompt)

        if result.success:
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            task.claude_session_id = result.session_id
            if self.run:
                self.run.completed_tasks += 1

            if github.has_changes(workspace):
                github.commit_and_push(workspace, f"feat: {task.title}", branch_name)

            await ws_manager.broadcast(self.project_id, {
                "type": "task_status_change",
                "payload": {"task_id": task.id, "status": "completed", "title": task.title},
            })

        elif result.is_partial:
            if github.has_changes(workspace):
                github.commit_and_push(workspace, f"wip: {task.title} (partial)", branch_name)
                await self._retry_task(task, result, runner, feature, user_story, workspace, branch_name, github)
            else:
                await self._handle_failure(task, result)

        else:
            await self._handle_failure(task, result)

        await self.db.commit()
        self._current_runner = None

    async def _retry_task(
        self, task, result, runner, feature, user_story, workspace, branch_name, github
    ):
        if task.retry_count >= settings.claude_max_retries:
            await self._handle_failure(task, result)
            return

        task.retry_count += 1
        modified = self._get_modified_files(workspace)
        prompt = self.prompt_builder.build_continuation_prompt(task, result.output, modified)

        retry_result = await runner.execute(prompt)
        if retry_result.success:
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            if self.run:
                self.run.completed_tasks += 1
            if github.has_changes(workspace):
                github.commit_and_push(workspace, f"feat: {task.title}", branch_name)
        else:
            await self._handle_failure(task, retry_result)

    async def _handle_failure(self, task: Task, result: ClaudeResult):
        task.retry_count += 1
        if task.retry_count >= settings.claude_max_retries:
            task.status = "failed"
            task.error_message = result.error[:2000]
            if self.run:
                self.run.failed_tasks += 1
            await ws_manager.broadcast(self.project_id, {
                "type": "task_status_change",
                "payload": {"task_id": task.id, "status": "failed", "error": result.error[:500]},
            })
        else:
            task.status = "pending"
            await ws_manager.broadcast(self.project_id, {
                "type": "task_status_change",
                "payload": {"task_id": task.id, "status": "retry", "retry_count": task.retry_count},
            })

    def _should_create_pr(self, task: Task, pr_strategy: str) -> bool:
        if task.status != "completed":
            return False
        return pr_strategy == "per_task"

    async def _create_pr(self, project, github, task, user_story, feature):
        branch = self._get_branch_name(task, user_story, feature, project.pr_strategy)
        repo_info = await github.validate_repo(project.github_repo_url)
        base = repo_info.get("default_branch", "main")

        title = f"feat: {task.title}"
        body = (
            f"## Task\n{task.title}\n\n"
            f"## User Story\n{user_story.title}\n\n"
            f"## Feature\n{feature.title}\n\n"
            f"Auto-generated by CodeGen Hub"
        )

        try:
            pr_data = await github.create_pull_request(
                project.github_repo_url, branch, base, title, body
            )
            pr = PullRequest(
                project_id=project.id,
                execution_run_id=self.run.id if self.run else None,
                github_pr_number=pr_data["number"],
                github_pr_url=pr_data["url"],
                branch_name=branch,
                title=title,
                scope_type="task",
                scope_id=task.id,
            )
            self.db.add(pr)
            await self.db.commit()

            await ws_manager.broadcast(self.project_id, {
                "type": "pr_created",
                "payload": {"pr_url": pr_data["url"], "pr_number": pr_data["number"], "title": title},
            })
        except Exception as e:
            logger.error(f"PR creation failed: {e}")

    async def _complete_run(self):
        if self.run:
            self.run.status = "completed"
            self.run.completed_at = datetime.utcnow()
            await self.db.commit()
        await ws_manager.broadcast(self.project_id, {
            "type": "execution_complete",
            "payload": {"status": "completed"},
        })

    async def _get_ordered_tasks(self) -> list[tuple[Task, UserStory, Feature]]:
        result = await self.db.execute(
            select(Feature)
            .where(Feature.project_id == self.project_id)
            .options(selectinload(Feature.user_stories).selectinload(UserStory.tasks))
            .order_by(Feature.order)
        )
        features = result.scalars().all()

        tasks = []
        for feature in features:
            for story in sorted(feature.user_stories, key=lambda s: s.order):
                for task in sorted(story.tasks, key=lambda t: t.order):
                    if task.status in ("pending", "in_progress"):
                        tasks.append((task, story, feature))
        return tasks

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
    def _get_modified_files(workspace: str) -> list[str]:
        from git import Repo
        try:
            repo = Repo(workspace)
            return [item.a_path for item in repo.index.diff(None)] + repo.untracked_files
        except Exception:
            return []
