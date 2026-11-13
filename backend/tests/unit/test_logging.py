import json

import pytest
import structlog

from app.core.logging import configure_logging


def test_logging_renderer_matches_environment(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("production")
    structlog.get_logger().info("production_event")
    production_output = capsys.readouterr().out
    assert json.loads(production_output)["event"] == "production_event"

    configure_logging("development")
    structlog.get_logger().info("development_event")
    development_output = capsys.readouterr().out
    assert "development_event" in development_output
    assert not development_output.lstrip().startswith("{")
