from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from surrealdb import RecordID

from app.core.record_ids import encode_rid


def rid(table: str) -> str:
    return encode_rid(RecordID(table, uuid4().hex), table)


async def same_not_found(
    client: AsyncClient,
    headers: dict[str, str],
    method: str,
    foreign: str,
    absent: str,
    **kwargs: Any,
) -> None:
    hidden = await client.request(method, foreign, headers=headers, **kwargs)
    missing = await client.request(method, absent, headers=headers, **kwargs)
    assert hidden.status_code == missing.status_code == 404, (method, foreign, hidden.text)
    assert hidden.json() == missing.json(), (method, foreign)
