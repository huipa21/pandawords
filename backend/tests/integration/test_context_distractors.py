import random
from uuid import uuid4

import pytest
from surrealdb import RecordID
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db import distractors as repository
from app.db.dictionary_schema_test_support import create, relate
from app.db.srs import user_record
from app.domain.exercises import DistractorCandidates, Unavailable
from app.services import distractors
from tests.conftest import UserFactory
from tests.integration.test_distractor_graph import entry, semantic, tag_pair

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["concept", "domain", "morph_group"])
async def test_context_tiers_authorize_each_membership_and_endpoint(
    db: AsyncWsSurrealConnection, make_user: UserFactory, kind: str
) -> None:
    alice, bob = await make_user(), await make_user()
    owner, foreign = user_record(alice.id), user_record(bob.id)
    answer = await entry(db, alice.id, frequency=0)
    safe = await entry(db, alice.id, frequency=0, private=owner, edge_owner=owner)
    synonym = await entry(db, alice.id, frequency=0)
    await tag_pair(db, answer, safe, kind, owner)
    await tag_pair(db, answer, synonym, kind, owner)
    await semantic(db, synonym, answer, "synonym", owner)
    tag = RecordID("tag", uuid4().hex)
    await create(db, tag, {"kind": kind, "name": "safe group", "owner": owner})
    await relate(db, "member_of", decode_rid(answer.sense_id, "sense"), tag, {"owner": owner})
    private = await entry(db, bob.id, frequency=0, private=foreign, edge_owner=foreign)
    assert isinstance(
        await distractors.choices(db, answer.model_copy(update={"sense_id": private.sense_id})),
        Unavailable,
    )
    foreign_edge = await entry(db, alice.id, frequency=0)
    for candidate, edge_owner in ((private, owner), (foreign_edge, foreign)):
        await relate(
            db,
            "member_of",
            decode_rid(candidate.sense_id, "sense"),
            tag,
            {"owner": edge_owner},
        )
    wrong_tag = await entry(db, alice.id, frequency=0)
    await tag_pair(db, answer, wrong_tag, kind, foreign)
    pool = await repository.candidate_pool(db, answer)
    assert pool is not None
    assert next(item.tier for item in pool.candidates if item.sense_id == safe.sense_id) == (
        1 if kind == "morph_group" else 0
    )
    result = await distractors.choices(db, answer, rng=random.Random(44))
    assert isinstance(result, DistractorCandidates)
    assert {item.id for item in result.choices} == {answer.sense_id, safe.sense_id}
    assert result == await distractors.choices(db, answer, rng=random.Random(44))
    await semantic(db, safe, answer, "synonym", owner)
    assert isinstance(await distractors.choices(db, answer), Unavailable)


async def test_context_tier_precedence_and_bounded_deterministic_selection(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice = await make_user()
    answer = await entry(db, alice.id)
    candidates = [await entry(db, alice.id, frequency=0) for _ in range(5)]
    for candidate in candidates[:2]:
        await tag_pair(db, answer, candidate, "concept")
        await tag_pair(db, answer, candidate, "morph_group")
    await tag_pair(db, answer, candidates[2], "morph_group")
    for candidate in candidates[3:]:
        await semantic(db, answer, candidate, "confusable")
    result = await distractors.choices(db, answer, rng=random.Random(17))
    assert isinstance(result, DistractorCandidates)
    assert len(result.choices) == 4
    assert {item.id for item in result.choices} == {
        answer.sense_id,
        *(candidate.sense_id for candidate in candidates[:3]),
    }
    assert result == await distractors.choices(db, answer, rng=random.Random(17))
