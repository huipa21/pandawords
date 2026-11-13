from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _dev_env_file() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    if not (project_root / ".git").exists():
        return project_root / ".env.dev"

    result = subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).parent / ".env.dev"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_dev_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    surreal_url: str = "ws://localhost:8100/rpc"
    surreal_test_url: str = "ws://localhost:8101/rpc"
    surreal_namespace: str = "pandawords"
    surreal_database: str = "dev"
    surreal_user: str = "root"
    surreal_pass: str = "change-me"
    surreal_timeout_seconds: float = Field(default=2.0, gt=0)

    @field_validator("surreal_url")
    @classmethod
    def validate_surreal_url(cls, value: str) -> str:
        if not value.startswith(("ws://", "wss://")):
            raise ValueError("SurrealDB requires a WebSocket URL")
        return value

    api_port: int = 8000
    web_dev_port: int = 5173
    public_base_url: str = "http://localhost:5173"
    app_env: Literal["development", "production"] = "development"

    jwt_secret: str = "replace-with-a-long-random-secret"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    admin_username: str = "admin"
    admin_password: str = "change-me"

    deepseek_api_key: str = "replace-with-your-api-key"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    target_language: str = "en"
    source_language: str = "zh"
    media_dir: Path = Path("data/media")
    lexicon_dir: Path = Path("data/lexicon")
    app_domain: str = "localhost"
    caddy_network: str = "pandawords"
    pixabay_api_key: str = "replace-with-your-api-key"
    audio_provider_order: str = "wiktionary,edge-tts"
    edge_tts_voice_us: str = "en-US-AriaNeural"
    edge_tts_voice_uk: str = "en-GB-SoniaNeural"

    pip_fallback_index_url: str = ""
    npm_fallback_registry: str = ""
    docker_registry_mirror: str = ""
