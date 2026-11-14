from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from surrealdb.types import Value

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db import content as repository
from app.db.auth import _atomic
from app.db.dictionary_schema_test_support import relate
from app.db.exercise_context import selected_context
from app.db.srs import user_record
from app.domain.content import ContentCreate
from app.domain.exercises import ExerciseContext, GeneratedExercise, Unavailable
from app.services import exercise_cloze
from app.services.exercise_answers import selected_lexeme_forms
from app.services.lexicon import LexiconReader
from tests.conftest import UserFactory
from tests.integration.srs_support import Study, create_study

pytestmark = pytest.mark.integration


@pytest.fixture
def test_settings(job_settings: Settings) -> Settings:
    return job_settings


@pytest.fixture
async def db(job_db: AsyncWsSurrealConnection) -> AsyncWsSurrealConnection:
    return job_db


async def selected(db: AsyncWsSurrealConnection, study: Study) -> ExerciseContext:
    async def operation(txn: UUID) -> ExerciseContext:
        return await selected_context(
            db,
            study.user.id,
            decode_rid(study.project.id, "project"),
            decode_rid(study.sense_id, "sense"),
            txn,
        )

    context = await _atomic(db, operation)
    return context.model_copy(
        update={"forms": selected_lexeme_forms(context.lemma, context.lexeme)}
    )


async def sentence(
    db: AsyncWsSurrealConnection, study: Study, text: str, *, start: int | None = None
) -> tuple[str, str]:
    row = await repository.create(db, study.user.id, "sentence", ContentCreate(text=text))
    start = text.index("running") if start is None else start

    async def operation(txn: UUID) -> str:
        return await repository.resolve(
            db,
            study.user.id,
            decode_rid(row.id, "sentence"),
            decode_rid(study.sense_id, "sense"),
            (start, start + 7),
            txn,
        )

    edge = await _atomic(db, operation)
    return row.id, edge


async def test_private_context_priority_isolation_deleted_and_hidden_links(
    db: AsyncWsSurrealConnection, make_user: UserFactory, lexicon_reader: LexiconReader
) -> None:
    alice = await create_study(db, make_user, lexicon_reader)
    bob = await create_study(db, make_user, lexicon_reader)
    alice_context, bob_context = await selected(db, alice), await selected(db, bob)
    text = "😀 Private: ＲＵＮ; running, ran."
    row, edge = await sentence(db, alice, text)
    generate = exercise_cloze.provider(db)
    result = await exercise_cloze.generate(alice_context, generate)
    assert isinstance(result, GeneratedExercise)
    assert result.prompt.text == "😀 Private: ____; ____, ____."
    other = await exercise_cloze.generate(bob_context, generate)
    assert isinstance(other, GeneratedExercise)
    assert "Private" not in other.prompt.text
    await repository.delete_link(
        db, alice.user.id, decode_rid(row, "sentence"), decode_rid(edge, "used_in")
    )
    deleted = await exercise_cloze.generate(alice_context, generate)
    assert isinstance(deleted, GeneratedExercise)
    assert deleted.prompt == other.prompt
    row, edge = await sentence(db, alice, text)
    await relate(
        db,
        "includes",
        decode_rid(alice.project.id, "project"),
        decode_rid(row, "sentence"),
        {"owner": user_record(alice.user.id), "hidden": True, "added_at": datetime.now(UTC)},
    )
    hidden = await exercise_cloze.generate(alice_context, generate)
    assert isinstance(hidden, GeneratedExercise)
    assert hidden.prompt == other.prompt
    await repository.delete_link(
        db, alice.user.id, decode_rid(row, "sentence"), decode_rid(edge, "used_in")
    )
    assert (await exercise_cloze.generate(alice_context, generate)) == hidden
    empty = alice_context.model_copy(
        update={"sense": alice_context.sense.model_copy(update={"fields": {"examples": []}})}
    )
    assert isinstance(await exercise_cloze.generate(empty, generate), Unavailable)


async def test_deleted_sentences_and_oversized_context_fall_back(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db import exercise_cloze as contexts

    alice = await create_study(db, make_user, lexicon_reader)
    context = await selected(db, alice)
    generate = exercise_cloze.provider(db)
    baseline = await exercise_cloze.generate(context, generate)
    row, _ = await sentence(db, alice, "Private running.")
    await repository.manage(db, alice.user.id, decode_rid(row, "sentence"), delete=True)
    assert await exercise_cloze.generate(context, generate) == baseline
    await sentence(db, alice, "Private running again.")
    await sentence(db, alice, "Still running privately.")
    monkeypatch.setattr(contexts, "LIMIT", 1)
    assert await exercise_cloze.generate(context, generate) == baseline


async def test_stale_span_and_foreign_owned_relation_or_endpoint_are_not_context(
    db: AsyncWsSurrealConnection, make_user: UserFactory, lexicon_reader: LexiconReader
) -> None:
    alice = await create_study(db, make_user, lexicon_reader)
    bob = await create_study(db, make_user, lexicon_reader)
    context = await selected(db, alice)
    context = context.model_copy(
        update={"sense": context.sense.model_copy(update={"fields": {"examples": []}})}
    )
    own = await repository.create(
        db, alice.user.id, "sentence", ContentCreate(text="Private running.")
    )
    foreign = await repository.create(
        db, bob.user.id, "sentence", ContentCreate(text="Bob running.")
    )
    for row, edge_owner, span in (
        (own, alice.user.id, [0, 7]),  # stale span points to "Private", not a selected form
        (own, bob.user.id, [8, 15]),
        (foreign, alice.user.id, [4, 11]),
    ):
        await relate(
            db,
            "used_in",
            decode_rid(alice.sense_id, "sense"),
            decode_rid(row.id, "sentence"),
            {"owner": user_record(edge_owner), "span": cast(Value, span)},
        )
    assert isinstance(
        await exercise_cloze.generate(context, exercise_cloze.provider(db)), Unavailable
    )
