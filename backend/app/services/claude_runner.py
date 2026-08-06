import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ClaudeResult:
    success: bool
    output: str = ""
    error: str = ""
    session_id: str = ""
    cost_usd: float = 0.0
    is_partial: bool = False


class ClaudeRunner:
    def __init__(self, workspace_path: str, max_budget_usd: float | None = None):
        self.workspace_path = workspace_path
        self.max_budget_usd = max_budget_usd or settings.claude_max_budget_usd
        self.timeout = settings.claude_timeout_seconds

    async def execute(self, prompt: str) -> ClaudeResult:
        cmd = self._build_command()
        shell_cmd = " ".join(cmd)
        logger.info(f"Executing Claude CLI in {self.workspace_path}")
        logger.info(f"Command: {shell_cmd}")
        logger.info(f"Prompt length: {len(prompt)} chars")

        try:
            result = await asyncio.to_thread(
                self._run_sync, shell_cmd, prompt
            )
            return result
        except Exception as e:
            logger.error(f"Claude CLI execution error: {type(e).__name__}: {e}")
            return ClaudeResult(success=False, error=str(e))

    def _run_sync(self, shell_cmd: str, prompt: str) -> ClaudeResult:
        try:
            proc = subprocess.run(
                shell_cmd,
                input=prompt,
                capture_output=True,
                text=True,
                cwd=self.workspace_path,
                timeout=self.timeout,
                shell=True,
            )

            output = proc.stdout
            error = proc.stderr
            exit_code = proc.returncode

            logger.info(f"Claude CLI exit code: {exit_code}")
            if output:
                logger.info(f"Claude CLI stdout (first 500): {output[:500]}")
            if error:
                logger.warning(f"Claude CLI stderr (first 500): {error[:500]}")

            if exit_code == 0:
                parsed = self._parse_json_output(output)
                return ClaudeResult(
                    success=True,
                    output=parsed.get("result", output),
                    session_id=parsed.get("session_id", ""),
                    cost_usd=parsed.get("cost_usd", 0.0),
                )
            else:
                return ClaudeResult(success=False, error=error or output)

        except subprocess.TimeoutExpired:
            logger.error(f"Claude CLI timed out after {self.timeout}s")
            return ClaudeResult(success=False, error="Timeout exceeded", is_partial=True)
        except FileNotFoundError:
            logger.error("Claude Code CLI not found in PATH")
            return ClaudeResult(
                success=False,
                error="Claude Code CLI not found. Ensure 'claude' is installed and in PATH.",
            )

    async def cancel(self):
        pass

    def _build_command(self) -> list[str]:
        claude_bin = self._find_claude_binary()
        return [
            claude_bin,
            "-p",
            "--output-format", "json",
            "--dangerously-skip-permissions",
            "--allowedTools", "Bash,Edit,Write,Read,Glob,Grep",
            "--max-budget-usd", str(self.max_budget_usd),
        ]

    @staticmethod
    def _find_claude_binary() -> str:
        npm_global = os.path.join(
            os.environ.get("APPDATA", ""),
            "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe",
        )
        if os.path.isfile(npm_global):
            return f'"{npm_global}"'
        return "claude"

    @staticmethod
    def _parse_json_output(output: str) -> dict:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            for line in output.strip().split("\n"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "result":
                        return data
                except json.JSONDecodeError:
                    continue
            return {"result": output}
