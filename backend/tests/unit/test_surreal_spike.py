from __future__ import annotations

import pytest

# isort: split
from app.db.spike import spike_endpoint


@pytest.mark.parametrize(
    "url",
    [
        "ws://localhost:8100/rpc",
        "ws://example.com:8101/rpc",
        "http://127.0.0.1:8101/rpc",
        "ws://127.0.0.1:8101/other",
        "ws://name:password@127.0.0.1:8101/rpc",
        "ws://127.0.0.1:8101/rpc?database=dev",
    ],
)
def test_spike_refuses_non_test_endpoints(url: str) -> None:
    with pytest.raises(ValueError):
        spike_endpoint(url)


def test_spike_uses_ipv4_for_localhost_websocket() -> None:
    assert spike_endpoint("ws://localhost:8101/rpc").geturl() == "ws://127.0.0.1:8101/rpc"


def test_spike_keeps_explicit_ipv6_loopback() -> None:
    assert spike_endpoint("ws://[::1]:8101/rpc").geturl() == "ws://[::1]:8101/rpc"
