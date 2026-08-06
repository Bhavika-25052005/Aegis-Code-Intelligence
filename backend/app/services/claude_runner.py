import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator

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


@dataclass
class ClaudeStreamEvent:
    type: str
    content: str = ""
    raw: dict = field(default_factory=dict)


class ClaudeRunner:
    def __init__(self, workspace_path: str, max_budget_usd: float | None = None):
        self.workspace_path = workspace_path
        self.max_budget_usd = max_budget_usd or settings.claude_max_budget_usd
        self.timeout = settings.claude_timeout_seconds
        self._process: asyncio.subprocess.Process | None = None

    async def execute(self, prompt: str) -> ClaudeResult:
        cmd = self._build_command(prompt)
        logger.info(f"Executing Claude CLI in {self.workspace_path}")

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                self._process.communicate(),
                timeout=self.timeout,
            )

            exit_code = self._process.returncode
            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")

            if exit_code == 0:
                result = self._parse_json_output(output)
                return ClaudeResult(
                    success=True,
                    output=result.get("result", output),
                    session_id=result.get("session_id", ""),
                    cost_usd=result.get("cost_usd", 0.0),
                )
            else:
                return ClaudeResult(success=False, error=error or output)

        except asyncio.TimeoutError:
            if self._process:
                self._process.kill()
            return ClaudeResult(success=False, error="Timeout exceeded", is_partial=True)
        except FileNotFoundError:
            return ClaudeResult(
                success=False,
                error="Claude Code CLI not found. Ensure 'claude' is installed and in PATH.",
            )
        except Exception as e:
            return ClaudeResult(success=False, error=str(e))

    async def execute_streaming(self, prompt: str) -> AsyncGenerator[ClaudeStreamEvent, None]:
        cmd = self._build_streaming_command(prompt)
        logger.info(f"Streaming Claude CLI in {self.workspace_path}")

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async for line in self._process.stdout:
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                try:
                    event_data = json.loads(line_str)
                    event_type = event_data.get("type", "unknown")

                    if event_type == "assistant":
                        content = ""
                        msg = event_data.get("message", {})
                        for block in msg.get("content", []):
                            if block.get("type") == "text":
                                content += block.get("text", "")
                        yield ClaudeStreamEvent(type="assistant", content=content, raw=event_data)

                    elif event_type == "result":
                        result_text = event_data.get("result", "")
                        yield ClaudeStreamEvent(type="result", content=result_text, raw=event_data)

                    else:
                        yield ClaudeStreamEvent(type=event_type, raw=event_data)

                except json.JSONDecodeError:
                    yield ClaudeStreamEvent(type="raw", content=line_str)

            await self._process.wait()

        except asyncio.TimeoutError:
            if self._process:
                self._process.kill()
            yield ClaudeStreamEvent(type="error", content="Timeout exceeded")
        except Exception as e:
            yield ClaudeStreamEvent(type="error", content=str(e))

    async def cancel(self):
        if self._process and self._process.returncode is None:
            self._process.kill()

    def _build_command(self, prompt: str) -> list[str]:
        return [
            "claude",
            "-p",
            "--output-format", "json",
            "--dangerously-skip-permissions",
            "--allowedTools", "Bash,Edit,Write,Read,Glob,Grep",
            "--max-budget-usd", str(self.max_budget_usd),
            prompt,
        ]

    def _build_streaming_command(self, prompt: str) -> list[str]:
        return [
            "claude",
            "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--allowedTools", "Bash,Edit,Write,Read,Glob,Grep",
            "--max-budget-usd", str(self.max_budget_usd),
            prompt,
        ]

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
