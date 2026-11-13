import subprocess
from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings


@pytest.mark.parametrize("field", ["surreal_url", "surreal_test_url"])
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("ws://localhost:8101/rpc", "ws://127.0.0.1:8101/rpc"),
        (
            "wss://user:pass@LOCALHOST:8101/rpc?host=localhost#localhost",
            "wss://user:pass@127.0.0.1:8101/rpc?host=localhost#localhost",
        ),
        ("ws://localhost/rpc", "ws://127.0.0.1/rpc"),
        ("wss://db.example.org:8101/rpc?host=localhost", None),
        ("ws://localhost.example.org:8101/rpc", None),
        ("ws://[::1]:8101/rpc", None),
    ],
)
def test_settings_normalize_only_literal_localhost(
    field: str, url: str, expected: str | None
) -> None:
    class TestSettings(Settings):
        model_config = SettingsConfigDict(env_file=None)

    settings = TestSettings.model_validate({field: url})

    assert getattr(settings, field) == (expected or url)


def test_settings_cover_env_example_keys() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_keys = {
        line.partition("=")[0]
        for line in (project_root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    configured_keys = {name.upper() for name in Settings.model_fields}

    assert env_keys <= configured_keys


def test_settings_resolve_the_main_worktree_env_file() -> None:
    project_root = Path(__file__).resolve().parents[3]
    if not (project_root / ".git").exists():
        expected_root = project_root
    else:
        result = subprocess.run(
            ["git", "-C", str(project_root), "worktree", "list", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        main_worktree = next(
            line.removeprefix("worktree ")
            for line in result.stdout.splitlines()
            if line.startswith("worktree ")
        )
        expected_root = Path(main_worktree)

    assert Settings.model_config.get("env_file") == expected_root / ".env.dev"


def test_settings_load_env_file_and_prefer_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    example_file = Path(__file__).resolve().parents[3] / ".env.example"
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("API_PORT", "8123")

    class ExampleSettings(Settings):
        model_config = SettingsConfigDict(env_file=example_file)

    settings = ExampleSettings()

    assert settings.api_port == 8123
    assert settings.web_dev_port == 5173
