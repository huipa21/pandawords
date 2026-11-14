import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.record_ids import encode_rid
from app.db import exercise_test_support as probe
from app.db import media_test_support
from app.db.study_plan_test_support import schedule
from app.domain.exercises import GeneratedExercise, Unavailable
from app.services import exercise_image, images, media, srs
from app.services.exercise_recall import build_registry
from app.services.exercise_registry import ExerciseRegistry
from app.services.lexicon import LexiconReader
from tests.api.auth_support import bearer, login
from tests.api.test_exercise_attempts import URL, assert_no_key, issue
from tests.api.test_recall_attempts import context
from tests.conftest import UserFactory
from tests.exercise_support import FakeGenerator, plugins
from tests.integration.srs_support import Study, create_study
from tests.unit.test_image_validation import picture

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def image_directory(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = Path.cwd() / (".image-review-" + uuid4().hex)
    root.mkdir()
    monkeypatch.setattr(test_settings, "media_dir", root)
    yield root
    shutil.rmtree(root)


@pytest.fixture
async def study(
    db: AsyncSurrealConnection, make_user: UserFactory, lexicon_reader: LexiconReader
) -> Study:
    study = await create_study(db, make_user, lexicon_reader)
    card = await srs.read_memory(db, study.user.id, study.sense_id)
    await schedule(db, study.user.id, card, datetime.now(UTC))
    return study


@pytest.mark.parametrize(
    "answer,correct",
    [(" ＲＵＮ ", True), ("ran", True), ("running", True), ("walk", False), (None, False)],
)
async def test_image_attempt_grades_after_toggle_and_confirms_once(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    study: Study,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    make_user: UserFactory,
    answer: str | None,
    correct: bool,
) -> None:
    def registry(*_args: object) -> ExerciseRegistry:
        target = ExerciseRegistry()
        exercise_image.register(target, db, test_settings)
        return target

    assert build_registry(db, test_settings, "US").get("image2word").kind == "recall"
    monkeypatch.setattr("app.api.exercise_attempts.build_registry", registry)
    image = await images.attach(
        db,
        test_settings,
        study.sense_id,
        study.user.id,
        uuid4().hex,
        picture(),
        "image/png",
        attribution="Photo by Alice · https://pixabay.com/photos/123/",
    )
    headers, opened = await issue(client, study)
    assert opened["exercise"] == "image2word" and opened["kind"] == "recall"
    assert opened["prompt"]["media_id"] == image.id
    assert opened["prompt"]["text"] == "" and opened["prompt"]["choices"] == []
    assert "run" not in str(opened["prompt"]).lower()
    assert_no_key(opened)
    other = await make_user()
    foreign = bearer(await login(client, other.username))
    path = f"{URL}/{opened['id']}"
    assert (await client.get(path, headers=foreign)).status_code == 404
    assert (await client.get(f"/api/media/{image.id}", headers=foreign)).status_code == 404
    assert (await client.get(f"/api/media/{image.id}", headers=headers)).content == picture()
    toggled = await client.patch(
        "/api/auth/me/review-preferences",
        headers=headers,
        json={"review_images_enabled": False, "review_audio_enabled": False, "accent": "UK"},
    )
    assert toggled.status_code == 200
    assert (
        await client.post(
            URL,
            headers=headers,
            json={
                "project_id": study.project.id,
                "sense_id": study.sense_id,
            },
        )
    ).status_code == 409
    # Deletion after issuance must not invalidate the private grading specification.
    await images.remove(db, test_settings, study.sense_id, study.user.id, image.id)
    body: dict[str, int | str] = {"duration_ms": 0}
    if answer is not None:
        body["answer"] = answer
    response = await client.post(
        path + ("/giveup" if answer is None else "/answer"),
        headers=headers,
        json=body,
    )
    assert response.status_code == 200, response.text
    assert response.json()["feedback"]["correct"] is correct
    receipts = [
        await client.post(path + "/confirm", headers=headers, json={"rating": 3}) for _ in range(2)
    ]
    assert all(receipt.status_code == 200 for receipt in receipts)
    assert receipts[0].json()["receipt"] == receipts[1].json()["receipt"]
    assert len(await probe.logs(db, study.user.id)) == 1


async def test_stable_exact_owner_images_skip_missing_corrupt_and_attribution_leaks(
    db: AsyncSurrealConnection,
    study: Study,
    test_settings: Settings,
    make_user: UserFactory,
    lexicon_reader: LexiconReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = await context(db, study)
    other = await create_study(db, make_user, lexicon_reader)
    foreign = await images.attach(
        db, test_settings, study.sense_id, other.user.id, uuid4().hex, picture(), "image/png"
    )
    assert isinstance(await exercise_image.generate(db, test_settings, source), Unavailable)
    attached = []
    for _ in range(3):
        attached.append(
            await images.attach(
                db,
                test_settings,
                study.sense_id,
                study.user.id,
                uuid4().hex,
                picture(),
                "image/png",
            )
        )
    attached.sort(key=lambda item: item.id)
    selected = await exercise_image.generate(db, test_settings, source)
    assert isinstance(selected, GeneratedExercise) and selected.prompt.media_id == attached[0].id
    for image, content in ((attached[0], None), (attached[1], b"not-an-image")):
        _, _, path = await media.delivery(db, test_settings, image.id, study.user.id)
        if content is None:
            path.unlink()
        else:
            path.write_bytes(content)
    selected = await exercise_image.generate(db, test_settings, source)
    assert isinstance(selected, GeneratedExercise) and selected.prompt.media_id == attached[2].id
    await images.remove(db, test_settings, study.sense_id, study.user.id, attached[2].id)
    leaking = await images.attach(
        db,
        test_settings,
        study.sense_id,
        study.user.id,
        uuid4().hex,
        picture(),
        "image/png",
        attribution="Photo by %72%75%6e · https://example.com/123",
    )
    assert isinstance(await exercise_image.generate(db, test_settings, source), Unavailable)

    # Even a malicious candidate provider cannot bypass the second authorization check.
    async def foreign_list(*_args: object) -> list:
        return [foreign]

    monkeypatch.setattr(images, "list_images", foreign_list)
    assert isinstance(await exercise_image.generate(db, test_settings, source), Unavailable)
    assert leaking.id != foreign.id
    wrong_sense = await media_test_support.sense(db, study.user.id)
    wrong_target = await images.attach(
        db,
        test_settings,
        encode_rid(wrong_sense, "sense"),
        study.user.id,
        uuid4().hex,
        picture(),
        "image/png",
    )

    async def wrong_target_list(*_args: object) -> list:
        return [wrong_target]

    monkeypatch.setattr(images, "list_images", wrong_target_list)
    assert isinstance(await exercise_image.generate(db, test_settings, source), Unavailable)


async def test_preferences_preserve_recognition_states_and_fallback(
    db: AsyncSurrealConnection,
    study: Study,
    test_settings: Settings,
) -> None:
    from fsrs import State

    from tests.unit.test_exercise_framework import memory

    source = await context(db, study)
    await images.attach(
        db, test_settings, study.sense_id, study.user.id, uuid4().hex, picture(), "image/png"
    )
    target = plugins(FakeGenerator("recognition", "recognition"), FakeGenerator("listen", "recall"))
    exercise_image.register(target, db, test_settings)
    for state in (State.Learning, State.Relearning):
        selected = await target.select(source, memory(state), random_value=lambda: 0)
        assert selected.plugin.exercise == "recognition"
    selected = await target.select(
        source, memory(State.Review, introduced=False), random_value=lambda: 0
    )
    assert selected.plugin.exercise == "recognition"
    for disabled in (
        frozenset({"image2word"}),
        frozenset({"listen"}),
        frozenset({"image2word", "listen"}),
    ):
        selected = await target.select(
            source, memory(State.Review), random_value=lambda: 0, disabled=disabled
        )
        assert selected.plugin.exercise not in disabled
        assert target.get("image2word").grade is not None
