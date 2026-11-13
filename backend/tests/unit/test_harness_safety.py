import pytest

from app.core.config import Settings
from app.db.test_support import isolated_database


@pytest.mark.parametrize(
    "overrides",
    [
        {"surreal_namespace": "pandawords", "surreal_database": "dev"},
        {"surreal_namespace": "pandawords_test", "surreal_database": "dev"},
        {
            "surreal_url": "ws://127.0.0.1:8100/rpc",
            "surreal_test_url": "ws://127.0.0.1:8100/rpc",
            "surreal_namespace": "pandawords_test",
            "surreal_database": "t_safety_01234567",
        },
    ],
)
async def test_harness_refuses_development_targets(overrides: dict[str, str]) -> None:
    settings = Settings().model_copy(update=overrides)
    with pytest.raises(ValueError):
        async with isolated_database(settings, migrate=True):
            pytest.fail("Unsafe settings must be rejected before connecting")
