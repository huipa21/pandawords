import random
from uuid import uuid4

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid, encode_rid
from app.db import distractors as repository
from app.db.dictionary import read_records
from app.db.dictionary_schema_test_support import create, relate
from app.db.srs import user_record
from app.domain.exercises import DistractorCandidates, ExerciseContext, Unavailable
from app.domain.overrides import OverrideFields, OverrideUpdate
from app.services import distractors, overrides
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration


async def entry(
    db: AsyncWsSurrealConnection,
    owner: str,
    *,
    frequency: float = 4.5,
    private: RecordID | None = None,
    edge_owner: RecordID | None = None,
    pos: str = "noun",
) -> ExerciseContext:
    key = uuid4().hex
    lemma, lexeme, sense = (RecordID(table, key) for table in ("lemma", "lexeme", "sense"))
    await create(
        db,
        lemma,
        {
            "text": key,
            "lang": "en",
            "kind": "word",
            "freq_zipf": frequency,
            "exam_tags": [],
            "source": "test",
            "owner": private,
        },
    )
    await create(
        db,
        lexeme,
        {
            "pos": pos,
            "etymology_no": 1,
            "forms": [],
            "pron": [],
            "owner": private,
        },
    )
    await create(
        db,
        sense,
        {
            "definition": f"meaning {key}",
            "gloss": {},
            "register": [],
            "domain": [],
            "examples": [],
            "rank": 0,
            "common": False,
            "source": "test",
            "owner": private,
        },
    )
    await relate(db, "has_lexeme", lemma, lexeme, {"owner": edge_owner})
    await relate(db, "has_sense", lexeme, sense, {"owner": edge_owner, "rank": 0})
    records = await read_records(db, owner, [lemma, lexeme, sense])
    return ExerciseContext(
        owner=owner,
        project_id="unused",
        sense_id=encode_rid(sense, "sense"),
        lemma=records[0],
        lexeme=records[1],
        sense=records[2],
        forms=(),
    )


async def tag_pair(
    db: AsyncWsSurrealConnection,
    answer: ExerciseContext,
    candidate: ExerciseContext,
    kind: str,
    owner: RecordID | None = None,
) -> None:
    tag = RecordID("tag", uuid4().hex)
    await create(db, tag, {"kind": kind, "name": kind, "owner": owner})
    for context in (answer, candidate):
        await relate(db, "member_of", decode_rid(context.sense_id, "sense"), tag, {"owner": owner})


async def semantic(
    db: AsyncWsSurrealConnection,
    start: ExerciseContext,
    end: ExerciseContext,
    kind: str,
    owner: RecordID | None = None,
) -> None:
    await relate(
        db,
        "relates_to",
        decode_rid(start.sense_id, "sense"),
        decode_rid(end.sense_id, "sense"),
        {"type": kind, "source": "test", "owner": owner},
    )


@pytest.mark.parametrize(
    "kind,tier",
    [("concept", 0), ("domain", 0), ("morph_group", 1), ("confusable", 2), ("frequency", 3)],
)
async def test_real_graph_ranking_tiers(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    kind: str,
    tier: int,
) -> None:
    user = await make_user()
    answer = await entry(db, user.id)
    candidate = await entry(db, user.id, frequency=4.999 if tier == 3 else 0)
    if kind == "confusable":
        await semantic(db, candidate, answer, "confusable")
    elif kind != "frequency":
        await tag_pair(db, answer, candidate, kind)
    pool = await repository.candidate_pool(db, answer)
    assert pool is not None
    actual = next(item.tier for item in pool.candidates if item.sense_id == candidate.sense_id)
    assert actual == tier
    result = await distractors.choices(db, answer, rng=random.Random(1))
    assert isinstance(result, DistractorCandidates)
    assert candidate.sense_id in {choice.id for choice in result.choices}
    assert result == await distractors.choices(db, answer, rng=random.Random(1))


async def test_private_senses_edges_tags_and_overrides_are_isolated(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
) -> None:
    alice, bob = await make_user(), await make_user()
    bob_id = user_record(bob.id)
    answer = await entry(db, alice.id, frequency=0)
    safe = await entry(db, alice.id, frequency=0)
    await semantic(db, answer, safe, "confusable")
    private = await entry(db, bob.id, frequency=0, private=bob_id)
    await semantic(db, answer, private, "confusable")
    await tag_pair(db, answer, private, "concept")
    private_edge = await entry(db, alice.id, frequency=0)
    await semantic(db, answer, private_edge, "confusable", bob_id)
    private_tag = await entry(db, alice.id, frequency=0)
    await tag_pair(db, answer, private_tag, "concept", bob_id)
    hidden_ancestry = await entry(db, alice.id, frequency=0, edge_owner=bob_id)
    await semantic(db, answer, hidden_ancestry, "confusable")
    await overrides.write(
        db,
        bob.id,
        "sense",
        safe.sense_id,
        OverrideUpdate(fields=OverrideFields(definition="bob private override")),
        action="patch",
    )
    await overrides.write(
        db,
        alice.id,
        "sense",
        safe.sense_id,
        OverrideUpdate(fields=OverrideFields(definition="alice effective definition")),
        action="patch",
    )
    result = await distractors.choices(db, answer, label="definition")
    assert isinstance(result, DistractorCandidates)
    assert {choice.id for choice in result.choices} == {answer.sense_id, safe.sense_id}
    assert {choice.label for choice in result.choices} == {
        str(answer.sense.fields["definition"]),
        "alice effective definition",
    }


@pytest.mark.parametrize("incoming", [False, True])
async def test_synonyms_both_directions_and_private_synonym_edges(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    incoming: bool,
) -> None:
    alice, bob = await make_user(), await make_user()
    answer = await entry(db, alice.id, frequency=0)
    synonym = await entry(db, alice.id, frequency=0)
    safe = await entry(db, alice.id, frequency=0)
    for candidate in (synonym, safe):
        await tag_pair(db, answer, candidate, "concept")
    await semantic(db, *((synonym, answer) if incoming else (answer, synonym)), "synonym")
    await semantic(db, answer, safe, "synonym", user_record(bob.id))
    result = await distractors.choices(db, answer)
    assert isinstance(result, DistractorCandidates)
    assert {choice.id for choice in result.choices} == {answer.sense_id, safe.sense_id}


async def test_effective_duplicate_definitions_and_missing_data(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
) -> None:
    user = await make_user()
    answer = await entry(db, user.id, frequency=0)
    assert isinstance(await distractors.choices(db, answer), Unavailable)
    candidate = await entry(db, user.id, frequency=0)
    await semantic(db, answer, candidate, "confusable")
    await overrides.write(
        db,
        user.id,
        "sense",
        candidate.sense_id,
        OverrideUpdate(
            fields=OverrideFields(definition=str(answer.sense.fields["definition"]).upper())
        ),
        action="patch",
    )
    assert isinstance(await distractors.choices(db, answer, label="definition"), Unavailable)
    assert isinstance(await distractors.choices(db, answer), DistractorCandidates)


async def test_own_private_candidates_and_oversized_safety_set(
    db: AsyncWsSurrealConnection,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user()
    answer = await entry(db, user.id, frequency=0)
    candidate = await entry(
        db,
        user.id,
        frequency=0,
        private=user_record(user.id),
        edge_owner=user_record(user.id),
    )
    await semantic(db, answer, candidate, "confusable", user_record(user.id))
    result = await distractors.choices(db, answer)
    assert isinstance(result, DistractorCandidates)
    assert {choice.id for choice in result.choices} == {answer.sense_id, candidate.sense_id}
    for _ in range(3):
        synonym = await entry(db, user.id, frequency=0)
        await semantic(db, answer, synonym, "synonym")
    monkeypatch.setattr(repository, "LIMIT", 2)
    assert isinstance(await distractors.choices(db, answer), Unavailable)
