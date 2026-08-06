import os
import re
from pathlib import Path

import httpx
from git import Repo


class GitHubService:
    def __init__(self, pat: str):
        self.pat = pat
        self.headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def validate_repo(self, repo_url: str) -> dict:
        owner, repo = self._parse_repo_url(repo_url)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=self.headers,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"name": data["full_name"], "default_branch": data["default_branch"]}

    async def clone_repo(self, repo_url: str, workspace_dir: str) -> str:
        owner, repo_name = self._parse_repo_url(repo_url)
        clone_path = str(Path(workspace_dir) / repo_name)

        auth_url = f"https://{self.pat}@github.com/{owner}/{repo_name}.git"

        if Path(clone_path).exists():
            git_repo = Repo(clone_path)
            git_repo.remotes.origin.pull()
        else:
            Repo.clone_from(auth_url, clone_path)

        return clone_path

    async def list_branches(self, repo_url: str) -> list[str]:
        owner, repo = self._parse_repo_url(repo_url)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/branches",
                headers=self.headers,
                timeout=15.0,
            )
            resp.raise_for_status()
            return [b["name"] for b in resp.json()]

    async def create_pull_request(
        self, repo_url: str, branch: str, base: str, title: str, body: str
    ) -> dict:
        owner, repo = self._parse_repo_url(repo_url)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                headers=self.headers,
                json={"title": title, "body": body, "head": branch, "base": base},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "number": data["number"],
                "url": data["html_url"],
                "state": data["state"],
            }

    def create_branch(self, repo_path: str, branch_name: str, base_branch: str = "main"):
        repo = Repo(repo_path)
        if branch_name in repo.heads:
            repo.heads[branch_name].checkout()
        else:
            base = repo.heads[base_branch] if base_branch in repo.heads else repo.active_branch
            repo.create_head(branch_name, base).checkout()

    def commit_and_push(self, repo_path: str, message: str, branch_name: str):
        repo = Repo(repo_path)
        if repo.is_dirty(untracked_files=True):
            repo.git.add(A=True)
            repo.index.commit(message)
        repo.remotes.origin.push(branch_name)

    def has_changes(self, repo_path: str) -> bool:
        repo = Repo(repo_path)
        return repo.is_dirty(untracked_files=True)

    @staticmethod
    def _parse_repo_url(url: str) -> tuple[str, str]:
        patterns = [
            r"github\.com[:/]([^/]+)/([^/.]+)",
            r"^([^/]+)/([^/]+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        raise ValueError(f"Cannot parse GitHub repo URL: {url}")
