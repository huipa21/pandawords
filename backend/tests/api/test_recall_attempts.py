import asyncio
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db import audio, media_test_support
from app.db import exercise_test_support as probe
from app.db.auth import _atomic
from app.db.exercise_context import selected_context
from app.db.srs import user_record
from app.db.study_plan_test_support import schedule
from app.domain.exercises import ExerciseContext, Unavailable
from app.domain.lexicon import Accent
from app.domain.media import MediaCreate
from app.domain.overrides import OverrideFields, OverrideUpdate
from app.services import exercise_cloze, exercise_listen, media, overrides, srs
from app.services.exercise_answers import selected_lexeme_forms
from app.services.exercise_registry import ExerciseRegistry
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.api.test_exercise_attempts import URL, assert_no_key, issue
from tests.conftest import UserFactory
from tests.integration.srs_support import Study, create_study

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def recall_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    def build_registry(
        db: AsyncSurrealConnection, settings: Settings, accent: Accent
    ) -> ExerciseRegistry:
        target = ExerciseRegistry()
        exercise_cloze.register(target)
        exercise_listen.register(target, exercise_listen.provider(db, settings, accent))
        return target

    monkeypatch.setattr("app.api.exercise_attempts.build_registry", build_registry)


@pytest.fixture(autouse=True)
def media_directory(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = Path.cwd() / (".recall-media-" + uuid4().hex)
    root.mkdir()
    monkeypatch.setattr(test_settings, "media_dir", root)
    yield root
    shutil.rmtree(root)


@pytest.fixture
async def study(
    db: AsyncSurrealConnection, make_user: UserFactory, lexicon_reader: LexiconReader
) -> Study:
    result = await create_study(db, make_user, lexicon_reader)
    card = await srs.read_memory(db, result.user.id, result.sense_id)
    await schedule(db, result.user.id, card, datetime.now(UTC))
    return result


async def context(db: AsyncSurrealConnection, study: Study) -> ExerciseContext:
    async def operation(txn: UUID) -> ExerciseContext:
        return await selected_context(
            db,
            study.user.id,
            decode_rid(study.project.id, "project"),
            decode_rid(study.sense_id, "sense"),
            txn,
        )

    source = await _atomic(db, operation)
    return source.model_copy(update={"forms": selected_lexeme_forms(source.lemma, source.lexeme)})


async def examples(db: AsyncSurrealConnection, study: Study, values: list[str]) -> None:
    await overrides.write(
        db,
        study.user.id,
        "sense",
        study.sense_id,
        OverrideUpdate(fields=OverrideFields(examples=values)),
        action="put",
    )


@pytest.mark.parametrize(
    "answer,correct", [(" RUN\t", True), ("ran", True), ("running", True), ("walk", False)]
)
async def test_real_cloze_attempt_server_grades_selected_forms(
    client: AsyncClient, db: AsyncSurrealConnection, study: Study, answer: str, correct: bool
) -> None:
    await examples(db, study, ["A runner was running; then ran."])
    headers, opened = await issue(client, study)
    assert opened["exercise"] == "cloze"
    assert opened["prompt"]["text"] == "a runner was ____; then ____."
    assert_no_key(opened)
    path = f"{URL}/{opened['id']}"
    assert_no_key((await client.get(path, headers=headers)).json())
    response = await client.post(
        path + "/answer", headers=headers, json={"answer": answer, "duration_ms": 0}
    )
    assert response.status_code == 200, response.text
    assert response.json()["feedback"]["correct"] is correct
    assert await probe.logs(db, study.user.id) == []
    confirmed = await client.post(path + "/confirm", headers=headers, json={"rating": 3})
    assert confirmed.status_code == 200, confirmed.text
    assert len(await probe.logs(db, study.user.id)) == 1


async def recording(
    db: AsyncSurrealConnection, settings: Settings, source: ExerciseContext, accent: Accent
) -> str:
    lexeme = decode_rid(source.lexeme.id, "lexeme")
    stored = await media.store(
        db,
        settings,
        MediaCreate(
            target=lexeme, kind="audio", mime="audio/mpeg", source="wiktionary", accent=accent
        ),
        b"offline-pronunciation",
    )
    await audio.attach(db, lexeme, accent, decode_rid(stored.id, "media"))
    return stored.id


@pytest.mark.parametrize("accent", ["US", "UK"])
@pytest.mark.parametrize("answer,correct", [("\tRUN ", True), ("running", False)])
async def test_listen_actual_authenticated_prompt_and_server_grade(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    test_settings: Settings,
    accent: Accent,
    answer: str,
    correct: bool,
) -> None:
    await examples(db, study, [])
    source = await context(db, study)
    chosen = await recording(db, test_settings, source, accent)
    other_accent: Accent = "UK" if accent == "US" else "US"
    await recording(db, test_settings, source, other_accent)
    headers = bearer(await login(client, study.user.username))
    updated = await client.patch(
        "/api/auth/me/review-preferences", headers=headers, json={"accent": accent}
    )
    assert updated.status_code == 200 and updated.json()["accent"] == accent
    _, opened = await issue(client, study)
    assert opened["exercise"] == "listen"
    assert opened["prompt"]["media_id"] == chosen
    assert opened["prompt"]["text"] == ""
    assert_no_key(opened)
    assert str(test_settings.media_dir) not in str(opened)
    response = await client.get(f"/api/media/{chosen}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert (await client.get(f"/api/media/{chosen}")).status_code == 401
    path = f"{URL}/{opened['id']}"
    graded = await client.post(
        path + "/answer", headers=headers, json={"answer": answer, "duration_ms": 0}
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["feedback"] == {"correct": correct, "answer": "run"}
    assert await probe.logs(db, study.user.id) == []
    _, abandoned = await issue(client, study)
    toggled = await client.patch(
        "/api/auth/me/review-preferences", headers=headers, json={"review_audio_enabled": False}
    )
    assert toggled.status_code == 200
    skipped = await client.post(
        URL,
        headers=headers,
        json={"project_id": study.project.id, "sense_id": study.sense_id},
    )
    assert skipped.status_code == 409
    gave_up = await client.post(
        f"{URL}/{abandoned['id']}/giveup", headers=headers, json={"duration_ms": 0}
    )
    assert gave_up.status_code == 200, gave_up.text
    assert gave_up.json()["feedback"] == {"correct": False, "answer": "run"}


async def test_private_missing_wrong_target_audio_and_override_spelling_skip(
    db: AsyncSurrealConnection,
    study: Study,
    test_settings: Settings,
    make_user: UserFactory,
    media_directory: Path,
) -> None:
    source = await context(db, study)
    rid = await recording(db, test_settings, source, "US")
    source = await context(db, study)
    provider = exercise_listen.provider(db, test_settings, "US")
    assert not isinstance(await provider(source), Unavailable)
    opposite = source.model_copy(
        update={
            "lexeme": source.lexeme.model_copy(
                update={"fields": {"pron": [{"accent": "US", "audio": rid}]}}
            )
        }
    )
    assert isinstance(
        await exercise_listen.provider(db, test_settings, "UK")(opposite), Unavailable
    )
    other = await make_user()
    record = decode_rid(rid, "media")
    await media_test_support.change(db, record, {"owner": user_record(other.id)})
    assert isinstance(await provider(source), Unavailable)
    await media_test_support.change(db, record, {"owner": None, "accent": "UK"})
    assert isinstance(await provider(source), Unavailable)
    await media_test_support.change(
        db, record, {"accent": "US", "target": decode_rid(source.lemma.id, "lemma")}
    )
    assert isinstance(await provider(source), Unavailable)
    await media_test_support.change(db, record, {"target": decode_rid(source.lexeme.id, "lexeme")})
    changed = source.model_copy(update={"forms": ("renamed",)})
    assert isinstance(await provider(changed), Unavailable)
    paths = await asyncio.to_thread(lambda: list(media_directory.rglob("*.mp3")))
    for path in paths:
        await asyncio.to_thread(path.unlink)
    assert isinstance(await provider(source), Unavailable)


async def test_missing_audio_only_skips_listening_and_private_examples_do_not_leak(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    make_user: UserFactory,
) -> None:
    await examples(db, study, ["We run."])
    source = await context(db, study)
    await overrides.write(
        db,
        study.user.id,
        "lexeme",
        source.lexeme.id,
        OverrideUpdate(fields=OverrideFields(pron=[])),
        action="put",
    )
    headers, opened = await issue(client, study)
    assert opened["exercise"] == "cloze"
    assert {"exercise": "listen", "reason": "missing_audio"} in opened["skipped"]
    stranger = await make_user()
    foreign = bearer(await login(client, stranger.username))
    assert (await client.get(f"{URL}/{opened['id']}", headers=foreign)).status_code == 404
    assert (await client.get(f"{URL}/{opened['id']}", headers=headers)).status_code == 200
    await examples(db, study, ["Only runners here."])
    response = await client.post(
        URL, headers=headers, json={"project_id": study.project.id, "sense_id": study.sense_id}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "exercise.no_usable"
