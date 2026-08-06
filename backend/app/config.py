import os
import tempfile
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./codegen_hub.db"

    workspace_path: str = ""
    encryption_key: str = ""

    claude_timeout_seconds: int = 300
    claude_max_retries: int = 3
    claude_max_budget_usd: float = 5.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_workspace_path(self) -> Path:
        if self.workspace_path:
            path = Path(self.workspace_path)
            path.mkdir(parents=True, exist_ok=True)
            return path
        return Path(tempfile.mkdtemp(prefix="codegen_hub_"))

    def get_encryption_key(self) -> bytes:
        if self.encryption_key:
            return self.encryption_key.encode()
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        self.encryption_key = key.decode()
        self._persist_encryption_key(key.decode())
        return key

    def _persist_encryption_key(self, key: str):
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            content = env_path.read_text()
            if "ENCRYPTION_KEY=" in content:
                lines = content.splitlines()
                lines = [l if not l.startswith("ENCRYPTION_KEY=") else f"ENCRYPTION_KEY={key}" for l in lines]
                env_path.write_text("\n".join(lines) + "\n")
            else:
                with open(env_path, "a") as f:
                    f.write(f"\nENCRYPTION_KEY={key}\n")
        else:
            env_path.write_text(f"ENCRYPTION_KEY={key}\n")


settings = Settings()
