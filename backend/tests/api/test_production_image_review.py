import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.db.study_plan_test_support import schedule
from app.services import srs
from tests.api.auth_support import bearer, login
from tests.conftest import UserFactory
from tests.unit.test_image_validation import picture

pytestmark = pytest.mark.integration


async def test_real_production_registry_deterministic_fixture_image_only(
    client: AsyncClient,
    db: AsyncSurrealConnection,
    make_user: UserFactory,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path.cwd() / (".production-image-" + uuid4().hex)
    root.mkdir()
    monkeypatch.setattr(test_settings, "media_dir", root)
    monkeypatch.setattr(
        test_settings,
        "lexicon_path",
        Path(__file__).parents[1] / "fixtures" / "lexicon_small.sqlite",
    )
    monkeypatch.setattr(test_settings, "llm_daily_budget", 0)
    monkeypatch.setattr(test_settings, "audio_network_enabled", False)
    try:
        user = await make_user()
        headers = bearer(await login(client, user.username))
        project = (
            await client.post("/api/projects", headers=headers, json={"name": "Image"})
        ).json()
        result = await client.post(
            "/api/dictionary/candidates", headers=headers, json={"text": "schedule"}
        )
        candidate = result.json()["candidates"][0]
        sense_key = candidate["lexemes"][0]["senses"][0]["id"]
        added = await client.post(
            f"/api/projects/{project['id']}/dictionary",
            headers=headers,
            json={"lemma_key": candidate["lemma"]["id"], "selected_senses": [sense_key]},
        )
        assert added.status_code == 200, added.text
        sense = added.json()["selected_sense_ids"][0]
        overridden = await client.put(
            f"/api/dictionary/sense/{sense}/override",
            headers=headers,
            json={"fields": {"definition": "", "gloss": {"zh": ""}, "examples": []}},
        )
        assert overridden.status_code == 200, overridden.text
        memory = await srs.read_memory(db, user.id, sense)
        await schedule(
            db,
            user.id,
            memory,
            datetime.now(UTC) - timedelta(minutes=1),
            last_review=datetime.now(UTC) - timedelta(days=14),
        )
        await client.patch(
            "/api/auth/me/review-preferences", headers=headers, json={"review_audio_enabled": False}
        )
        uploaded = await client.post(
            f"/api/images/senses/{sense}",
            headers={**headers, "Content-Type": "image/png", "request-id": uuid4().hex},
            content=picture(),
        )
        assert uploaded.status_code == 200, uploaded.text
        for _ in range(3):
            issued = await client.post(
                "/api/exercise-attempts",
                headers=headers,
                json={"project_id": project["id"], "sense_id": sense},
            )
            assert issued.status_code == 201, issued.text
            assert issued.json()["exercise"] == "image2word", issued.text
        await client.patch(
            "/api/auth/me/review-preferences",
            headers=headers,
            json={"review_images_enabled": False},
        )
        disabled = await client.post(
            "/api/exercise-attempts",
            headers=headers,
            json={"project_id": project["id"], "sense_id": sense},
        )
        assert disabled.status_code == 409, disabled.text
    finally:
        shutil.rmtree(root)
