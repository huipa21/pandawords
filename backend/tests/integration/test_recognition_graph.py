import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.record_ids import decode_rid
from app.db.dictionary import read_records
from app.db.dictionary_schema_test_support import relate
from app.db.srs import user_record
from app.domain.exercises import ExerciseContext, GeneratedExercise, Unavailable
from app.domain.overrides import OverrideFields, OverrideUpdate
from app.services import overrides, recognition
from app.services.exercise_registry import ExerciseRegistry
from tests.conftest import UserFactory
from tests.integration.test_distractor_graph import entry, semantic, tag_pair

pytestmark = pytest.mark.integration


async def effective(db: AsyncWsSurrealConnection, context: ExerciseContext) -> ExerciseContext:
    lemma, lexeme, sense = await read_records(
        db,
        context.owner,
        [
            decode_rid(context.lemma.id, "lemma"),
            decode_rid(context.lexeme.id, "lexeme"),
            decode_rid(context.sense_id, "sense"),
        ],
    )
    return context.model_copy(update={"lemma": lemma, "lexeme": lexeme, "sense": sense})


async def test_selected_sense_overrides_gloss_and_synonym_safety(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    answer, other, synonym = [await entry(db, alice.id, frequency=0) for _ in range(3)]
    for candidate in (other, synonym):
        await tag_pair(db, answer, candidate, "concept")
    await semantic(db, synonym, answer, "synonym")
    for user, value in ((alice, "owner meaning"), (bob, "private meaning")):
        await overrides.write(
            db,
            user.id,
            "sense",
            answer.sense_id,
            OverrideUpdate(fields=OverrideFields(definition=value)),
            action="patch",
        )
    provider = recognition.DatabaseProvider(db)
    target = ExerciseRegistry()
    recognition.register(target, provider)
    selected = await effective(db, answer)
    question = await target.get("def2word").generate(selected)
    assert isinstance(question, GeneratedExercise)
    assert question.prompt.text == "owner meaning"
    assert {item.label for item in question.prompt.choices} == {
        str(answer.lemma.fields["text"]),
        str(other.lemma.fields["text"]),
    }
    definition = await target.get("word2def").generate(selected)
    assert isinstance(definition, GeneratedExercise)
    assert {item.label for item in definition.prompt.choices} == {
        "owner meaning",
        str(other.sense.fields["definition"]),
    }
    # A distinct selected sense under the same lexeme must not reuse the first sense's meaning.
    second = await entry(db, alice.id, frequency=0)
    await relate(
        db,
        "has_sense",
        decode_rid(answer.lexeme.id, "lexeme"),
        decode_rid(second.sense_id, "sense"),
        {"rank": 1, "owner": None},
    )
    selected_second = selected.model_copy(
        update={"sense_id": second.sense_id, "sense": second.sense}
    )
    await tag_pair(db, second, other, "concept")
    question = await target.get("def2word").generate(selected_second)
    assert isinstance(question, GeneratedExercise)
    assert question.prompt.text == second.sense.fields["definition"]
    await overrides.write(
        db,
        alice.id,
        "sense",
        answer.sense_id,
        OverrideUpdate(fields=OverrideFields(definition="", gloss={"zh": "我的释义"})),
        action="patch",
    )
    gloss = await target.get("word2def").generate(await effective(db, answer))
    assert isinstance(gloss, GeneratedExercise)
    assert "我的释义" in {item.label for item in gloss.prompt.choices}


@pytest.mark.parametrize("kind", ["antonym", "synonym", "derives_to"])
@pytest.mark.parametrize("incoming", [False, True])
async def test_relation_direction_types_and_other_correct_answers(
    db: AsyncWsSurrealConnection, make_user: UserFactory, kind: str, incoming: bool
) -> None:
    alice = await make_user()
    source, answer, alternative, safe = [await entry(db, alice.id, frequency=0) for _ in range(4)]
    for candidate in (answer, alternative):
        await tag_pair(db, candidate, safe, "concept")
        await tag_pair(db, candidate, alternative if candidate == answer else answer, "concept")
        start, end = (candidate, source) if incoming else (source, candidate)
        if kind == "derives_to":
            await relate(
                db,
                kind,
                decode_rid(start.lexeme.id, "lexeme"),
                decode_rid(end.lexeme.id, "lexeme"),
                {"owner": None, "via": "suffix"},
            )
        else:
            await semantic(db, start, end, kind)
    provider = recognition.DatabaseProvider(db)
    questions = await provider.relations(source)
    assert len(questions) == 2
    assert all(f"by “{kind}”" in item.text for item in questions)
    assert all(("linked to" if incoming else "linked from") in item.text for item in questions)
    target = ExerciseRegistry()
    recognition.register(target, provider)
    generated = await target.get("relation").generate(source)
    assert isinstance(generated, GeneratedExercise)
    labels = {item.label for item in generated.prompt.choices}
    assert safe.lemma.fields["text"] in labels and len(labels) == 2
    assert source.lemma.fields["text"] not in labels
    assert not {str(answer.lemma.fields["text"]), str(alternative.lemma.fields["text"])} <= labels


async def test_private_relation_edges_endpoints_ancestry_and_overrides(
    db: AsyncWsSurrealConnection, make_user: UserFactory
) -> None:
    alice, bob = await make_user(), await make_user()
    bob_id = user_record(bob.id)
    source, safe, candidate = [await entry(db, alice.id, frequency=0) for _ in range(3)]
    provider = recognition.DatabaseProvider(db)
    target = ExerciseRegistry()
    recognition.register(target, provider)
    assert isinstance(await target.get("relation").generate(source), Unavailable)
    private = await entry(db, bob.id, frequency=0, private=bob_id)
    hidden = await entry(db, alice.id, frequency=0, edge_owner=bob_id)
    await semantic(db, source, private, "antonym")
    await semantic(db, source, hidden, "antonym")
    await semantic(db, source, candidate, "antonym", bob_id)
    for endpoint in (private, hidden):
        await relate(
            db,
            "derives_to",
            decode_rid(source.lexeme.id, "lexeme"),
            decode_rid(endpoint.lexeme.id, "lexeme"),
            {"owner": None},
        )
    await relate(
        db,
        "derives_to",
        decode_rid(source.lexeme.id, "lexeme"),
        decode_rid(candidate.lexeme.id, "lexeme"),
        {"owner": bob_id},
    )
    assert await provider.relations(source) == ()
    await semantic(db, source, candidate, "antonym")
    await tag_pair(db, candidate, safe, "concept")
    await overrides.write(
        db,
        bob.id,
        "lemma",
        candidate.lemma.id,
        OverrideUpdate(fields=OverrideFields(text="bob secret word")),
        action="patch",
    )
    generated = await target.get("relation").generate(source)
    assert isinstance(generated, GeneratedExercise)
    assert "bob secret word" not in generated.model_dump_json()
    assert {item.label for item in generated.prompt.choices} == {
        str(safe.lemma.fields["text"]),
        str(candidate.lemma.fields["text"]),
    }
    # Removing the only safe alternative makes the relation unavailable, not fabricated.
    await semantic(db, candidate, safe, "synonym")
    assert isinstance(await target.get("relation").generate(source), Unavailable)
