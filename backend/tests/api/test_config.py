from pathlib import Path

from app.core.config import Settings


def test_settings_cover_env_example_keys() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_keys = {
        line.partition("=")[0]
        for line in (project_root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    configured_keys = {name.upper() for name in Settings.model_fields}

    assert env_keys <= configured_keys
