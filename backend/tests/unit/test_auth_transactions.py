import asyncio
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import structlog
from anyio import CancelScope
from surrealdb import AsyncSurrealConnection

from app.db.auth import _atomic


async def test_rollback_failure_preserves_original_error_without_secrets() -> None:
    transaction = uuid4()
    connection = AsyncMock()
    connection.begin.return_value = transaction
    connection.cancel.side_effect = OSError("private-rollback-message")
    failure = ValueError("private-operation-message")

    async def operation(txn: UUID) -> None:
        assert txn == transaction
        raise failure

    with structlog.testing.capture_logs() as logs:
        with pytest.raises(ValueError) as error:
            await _atomic(cast(AsyncSurrealConnection, connection), operation)
    assert error.value is failure
    connection.cancel.assert_awaited_once_with(transaction)
    connection.commit.assert_not_awaited()
    assert any(
        log["event"] == "auth_transaction_rollback_failed" and log["error_type"] == "OSError"
        for log in logs
    )
    assert "private-" not in str(logs)


async def test_repeated_cancellation_waits_for_rollback() -> None:
    transaction = uuid4()
    connection = AsyncMock()
    connection.begin.return_value = transaction
    operating, rolling_back, release, completed = (asyncio.Event() for _ in range(4))

    async def operation(txn: UUID) -> None:
        operating.set()
        await asyncio.Event().wait()

    async def rollback(txn: UUID) -> None:
        assert txn == transaction
        rolling_back.set()
        await release.wait()
        completed.set()

    connection.cancel.side_effect = rollback
    task = asyncio.create_task(_atomic(cast(AsyncSurrealConnection, connection), operation))
    try:
        await asyncio.wait_for(operating.wait(), timeout=2)
        task.cancel()
        await asyncio.wait_for(rolling_back.wait(), timeout=2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert completed.is_set()
        connection.cancel.assert_awaited_once_with(transaction)
        connection.commit.assert_not_awaited()
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_anyio_cancellation_shields_transaction_rollback() -> None:
    transaction = uuid4()
    connection = AsyncMock()
    connection.begin.return_value = transaction
    completed = asyncio.Event()

    async def rollback(txn: UUID) -> None:
        assert txn == transaction
        await asyncio.sleep(0)
        completed.set()

    async def operation(txn: UUID) -> None:
        scope.cancel()
        await asyncio.sleep(0)

    connection.cancel.side_effect = rollback
    with CancelScope() as scope:
        await _atomic(cast(AsyncSurrealConnection, connection), operation)
        pytest.fail("Cancellation must not return a successful transaction")
    assert scope.cancelled_caught
    assert completed.is_set()
    connection.cancel.assert_awaited_once_with(transaction)
    connection.commit.assert_not_awaited()


async def test_cancellation_during_begin_rolls_back_returned_transaction() -> None:
    transaction = uuid4()
    connection = AsyncMock()
    beginning, release = asyncio.Event(), asyncio.Event()
    operation = AsyncMock()

    async def begin() -> UUID:
        beginning.set()
        await release.wait()
        return transaction

    connection.begin.side_effect = begin
    task = asyncio.create_task(_atomic(cast(AsyncSurrealConnection, connection), operation))
    try:
        await asyncio.wait_for(beginning.wait(), timeout=2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        connection.cancel.assert_awaited_once_with(transaction)
        connection.commit.assert_not_awaited()
        operation.assert_not_awaited()
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
