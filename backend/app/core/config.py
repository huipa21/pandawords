from __future__ import annotations

import subprocess
from ipaddress import ip_network
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
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

    surreal_url: str = "ws://127.0.0.1:8100/rpc"
    surreal_test_url: str = "ws://127.0.0.1:8101/rpc"
    surreal_namespace: str = "pandawords"
    surreal_database: str = "dev"
    surreal_user: str = "root"
    surreal_pass: str = "change-me"
    surreal_timeout_seconds: float = Field(default=2.0, gt=0)

    @field_validator("surreal_url", "surreal_test_url")
    @classmethod
    def validate_surreal_url(cls, value: str) -> str:
        if not value.startswith(("ws://", "wss://")):
            raise ValueError("SurrealDB requires a WebSocket URL")
        parts = urlsplit(value)
        if parts.hostname != "localhost":
            return value
        userinfo, separator, _ = parts.netloc.rpartition("@")
        authority = f"{userinfo}{separator}127.0.0.1"
        if parts.port is not None:
            authority += f":{parts.port}"
        return urlunsplit(parts._replace(netloc=authority))

    api_port: int = 8000
    web_dev_port: int = 5173
    public_base_url: str = "http://localhost:5173"
    app_env: Literal["development", "production"] = "development"
    app_version: str = "dev"
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    rate_limit_window_seconds: int = Field(default=60, gt=0, le=3600)
    rate_limit_capacity: int = Field(default=16384, gt=0, le=1000000)
    rate_limit_auth: int = Field(default=30, gt=0)
    rate_limit_anonymous: int = Field(default=60, gt=0)
    rate_limit_user: int = Field(default=600, gt=0)
    rate_limit_expensive: int = Field(default=120, gt=0)

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxies(cls, values: list[str]) -> list[str]:
        networks = [ip_network(value) for value in values]
        if any(network.prefixlen == 0 for network in networks):
            raise ValueError("Trust explicit proxy networks, never every address")
        return [str(network) for network in networks]

    jwt_secret: str = "replace-with-a-long-random-secret"
    jwt_access_ttl_minutes: int = Field(default=60, gt=0)
    jwt_refresh_ttl_days: int = Field(default=30, gt=0)
    admin_username: str = "admin"
    admin_password: str = "change-me"

    deepseek_api_key: str = "replace-with-your-api-key"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_daily_budget: int = Field(default=20, ge=0)
    llm_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    llm_max_retries: int = Field(default=1, ge=0, le=3)

    srs_recognition_fast_ms: int = Field(default=3000, ge=0, le=60000)
    srs_recognition_slow_ms: int = Field(default=12000, ge=0, le=60000)
    srs_recall_fast_ms: int = Field(default=5000, ge=0, le=60000)
    srs_recall_slow_ms: int = Field(default=20000, ge=0, le=60000)

    @model_validator(mode="after")
    def validate_srs_thresholds(self) -> Settings:
        if (
            self.srs_recognition_fast_ms > self.srs_recognition_slow_ms
            or self.srs_recall_fast_ms > self.srs_recall_slow_ms
        ):
            raise ValueError("SRS fast thresholds must not exceed slow thresholds")
        return self

    target_language: str = "en"
    source_language: str = "zh"
    media_dir: Path = Path("data/media")
    lexicon_dir: Path = Path("data/lexicon")
    lexicon_path: Path | None = None
    app_domain: str = "localhost"
    caddy_network: str = "pandawords"
    pixabay_api_key: str = "replace-with-your-api-key"
    audio_provider_order: str = "wiktionary,edge-tts"
    audio_network_enabled: bool = True
    wikimedia_user_agent: str = "PandaWords/0.1 (personal vocabulary app)"
    wikimedia_request_interval_seconds: float = Field(default=0.5, ge=0.5)
    audio_timeout_seconds: float = Field(default=30.0, gt=0)
    audio_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    edge_tts_voice_us: str = "en-US-AriaNeural"
    edge_tts_voice_uk: str = "en-GB-SoniaNeural"

    @field_validator("audio_provider_order")
    @classmethod
    def validate_audio_providers(cls, value: str) -> str:
        providers = [
            part.strip().replace("edge_tts", "edge-tts")
            for part in value.split(",")
            if part.strip()
        ]
        if providers not in ([], ["wiktionary"], ["edge-tts"], ["wiktionary", "edge-tts"]):
            raise ValueError("Audio providers must be wiktionary then optional edge-tts")
        return ",".join(providers)

    @field_validator("wikimedia_user_agent")
    @classmethod
    def validate_wikimedia_user_agent(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Expected a descriptive Wikimedia User-Agent")
        return value.strip()

    pip_fallback_index_url: str = ""
    npm_fallback_registry: str = ""
    docker_registry_mirror: str = ""
