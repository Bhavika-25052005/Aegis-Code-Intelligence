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
        return key


settings = Settings()
