from typing import Any

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db import dictionary_schema_test_support as schema
from app.db import media_test_support as support
from app.db import mnemonics as repository
from app.domain.jobs import JobRejected
from app.domain.mnemonics import MnemonicRequest
from app.services import jobs, llm, mnemonics
from tests.conftest import UserFactory
from tests.llm_support import provider as provider
from tests.llm_support import settings as settings
from tests.mnemonic_support import target

pytestmark = pytest.mark.integration


@pytest.fixture
def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def test_foreign_ancestry_never_enters_context(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    lemma = await target(db, "lemma", bob.id)
    lexeme, sense = await target(db, "lexeme"), await target(db)
    lr, xr, sr = (
        decode_rid(item["target_id"], item["target_table"]) for item in (lemma, lexeme, sense)
    )
    await schema.relate(db, "has_lexeme", lr, xr, {})
    await schema.relate(db, "has_sense", xr, sr, {"rank": 0})
    context = await repository.context(db, alice.id, sr)
    assert "lemma" not in context and context["pos"] == "verb"
    assert (await repository.context(db, bob.id, sr))["lemma"]


async def test_context_changed_during_generation_cannot_be_retrieved(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    settings: Settings,
    provider: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user()
    data = MnemonicRequest.model_validate(await target(db))
    record = decode_rid(data.target_id, "sense")
    provider["content"] = '{"text":"A useful hint."}'
    pending = await mnemonics.request(db, settings, owner.id, data)
    job = await jobs.claim(db)
    assert job is not None and job.id == pending.job_id
    generate = llm.generate_json

    async def changing(*args: Any, **kwargs: Any) -> Any:
        result = await generate(*args, **kwargs)
        await support.change(db, record, {"definition": "Changed during provider request"})
        return result

    monkeypatch.setattr(llm, "generate_json", changing)
    with pytest.raises(JobRejected, match="stale_content"):
        await mnemonics.generate_job(db, settings, job)
    result = await mnemonics.read(db, settings, owner.id, job.id)
    assert result.status == "unavailable" and result.reason == "stale_content"
    assert provider["calls"] == 1
