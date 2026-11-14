from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

import httpx
import pytest
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db import audio as repository
from app.db.jobs_test_support import make_due, worker_read
from app.domain.add_to_project import AudioJobPayload
from app.domain.identity import user_subject
from app.domain.jobs import JobCreate
from app.domain.media import MediaCreate
from app.services import audio, audio_sources, dictionary, jobs, media
from app.services.lexicon import LexiconReader
from app.worker.handlers import HANDLERS
from app.worker.runtime import run_once

_synthesize = audio_sources.synthesize

pytestmark = pytest.mark.integration


@pytest.fixture
def audio_settings(job_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    with TemporaryDirectory(dir=Path.cwd(), prefix=".audio-test-") as directory:
        # Neither an overlooked download nor real TTS may contact the network.
        def network_forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("Unmocked external audio call")

        monkeypatch.setattr(audio_sources, "recording", network_forbidden)
        monkeypatch.setattr(audio_sources, "synthesize", network_forbidden)
        yield job_settings.model_copy(
            update={
                "media_dir": Path(directory),
                "lexicon_path": Path(__file__).parents[1] / "fixtures" / "lexicon_small.sqlite",
                "audio_network_enabled": True,
                "audio_provider_order": "wiktionary,edge-tts",
                "edge_tts_voice_us": "test-US",
                "edge_tts_voice_uk": "test-UK",
            }
        )


async def payload(
    db: AsyncWsSurrealConnection, reader: LexiconReader, accent: str = "US"
) -> AudioJobPayload:
    result = await dictionary.materialize_lemma(db, reader, "schedule", selected_senses=[])
    return AudioJobPayload.model_validate(
        {
            "lemma_key": ["en", "schedule"],
            "lemma_id": result.lemma_id,
            "lexeme_id": result.lexeme_ids[0],
            "accent": accent,
        }
    )


async def test_registered_dispatch_source_cache_and_effective_entry(
    job_db: AsyncWsSurrealConnection,
    lexicon_reader: LexiconReader,
    audio_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = await payload(job_db, lexicon_reader)
    recording = AsyncMock(
        return_value=audio_sources.AudioContent(
            b"OggSsource",
            "audio/ogg",
            "wiktionary",
            "Speaker; CC BY-SA 4.0; Commons File:Schedule.ogg",
        )
    )
    monkeypatch.setattr(audio_sources, "recording", recording)
    assert "audio" in HANDLERS
    job = await jobs.enqueue(job_db, JobCreate(type="audio", payload=data.model_dump()))
    assert await run_once(job_db, settings=audio_settings)
    assert (await worker_read(job_db, job)).status == "done"
    assert recording.await_count == 1
    cached = await repository.cached(job_db, decode_rid(data.lexeme_id, "lexeme"), "US")
    assert len(cached) == 1 and cached[0].owner is None
    assert cached[0].source == "wiktionary"
    assert "Speaker" in (cached[0].attribution or "")
    # Another owner's independent job reuses shared bytes, not a new fetch/TTS.
    other_job = await jobs.enqueue(
        job_db,
        JobCreate(type="audio", owner=user_subject("second_owner"), payload=data.model_dump()),
    )
    assert await run_once(job_db, settings=audio_settings)
    assert (await worker_read(job_db, other_job)).status == "done"
    assert recording.await_count == 1
    assert len(list(audio_settings.media_dir.rglob("*.ogg"))) == 1
    entry = await dictionary.read_entry(job_db, user_subject("viewer"), data.lemma_id)
    assert entry is not None
    pronunciations = entry.lexemes[0].lexeme.fields["pron"]
    assert isinstance(pronunciations, list)
    us = next(pron for pron in pronunciations if isinstance(pron, dict) and pron["accent"] == "US")
    assert isinstance(us, dict) and isinstance(us["audio"], str)
    assert us["ipa"]
    read = await media.read(job_db, audio_settings, us["audio"], user_subject("different_viewer"))
    assert read.source == "wiktionary" and read.accent == "US"
    assert "path" not in read.model_dump()
    # A missing file must not leave a successful but unplayable cache result.
    (audio_settings.media_dir / cached[0].path).unlink()
    await audio.acquire(job_db, audio_settings, lexicon_reader, data)
    assert recording.await_count == 2
    entry = await dictionary.read_entry(job_db, user_subject("viewer"), data.lemma_id)
    assert entry is not None
    pron = entry.lexemes[0].lexeme.fields["pron"]
    assert isinstance(pron, list)
    new_us = next(item for item in pron if isinstance(item, dict) and item["accent"] == "US")
    assert isinstance(new_us, dict) and new_us["audio"] != us["audio"]


@pytest.mark.parametrize("accent,voice", [("US", "test-US"), ("UK", "test-UK")])
async def test_source_absence_falls_back_to_accent_voice(
    accent: str,
    voice: str,
    job_db: AsyncWsSurrealConnection,
    lexicon_reader: LexiconReader,
    audio_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = await payload(job_db, lexicon_reader, accent)
    monkeypatch.setattr(
        audio_sources, "recording", AsyncMock(side_effect=audio_sources.AudioUnavailable("missing"))
    )
    tts = AsyncMock(
        return_value=audio_sources.AudioContent(b"MP3", "audio/mpeg", "edge_tts", voice)
    )
    monkeypatch.setattr(audio_sources, "synthesize", tts)
    await audio.acquire(job_db, audio_settings, lexicon_reader, data)
    tts.assert_awaited_once_with(audio_settings, "schedule", voice)
    rows = await repository.cached(job_db, decode_rid(data.lexeme_id, "lexeme"), data.accent)
    assert len(rows) == 1 and rows[0].source == "edge_tts" and rows[0].attribution == voice


async def test_optional_absence_and_offline_jobs_complete_without_media(
    job_db: AsyncWsSurrealConnection,
    lexicon_reader: LexiconReader,
    audio_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = await payload(job_db, lexicon_reader)
    monkeypatch.setattr(
        audio_sources, "recording", AsyncMock(side_effect=audio_sources.AudioUnavailable("missing"))
    )
    # Real synthesize handles blank voice before constructing an external client.
    with monkeypatch.context() as patch:
        patch.setattr(audio_sources, "synthesize", _synthesize)
        job = await jobs.enqueue(job_db, JobCreate(type="audio", payload=data.model_dump()))
        assert await run_once(
            job_db, settings=audio_settings.model_copy(update={"edge_tts_voice_us": ""})
        )
        assert (await worker_read(job_db, job)).status == "done"
    no_network = audio_settings.model_copy(update={"audio_network_enabled": False})
    await audio.acquire(job_db, no_network, lexicon_reader, data)
    assert not list(audio_settings.media_dir.rglob("*.mp3"))
    assert not await repository.cached(job_db, decode_rid(data.lexeme_id, "lexeme"), "US")


@pytest.mark.parametrize("failure", ["transient", "bug"])
async def test_dispatch_retries_transient_and_does_not_swallow_arbitrary_errors(
    failure: str,
    job_db: AsyncWsSurrealConnection,
    lexicon_reader: LexiconReader,
    audio_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = await payload(job_db, lexicon_reader)
    request = httpx.Request("GET", "https://commons.wikimedia.org/w/api.php")
    exc = (
        httpx.HTTPStatusError(
            "temporary", request=request, response=httpx.Response(503, request=request)
        )
        if failure == "transient"
        else RuntimeError("programming_error")
    )
    recording = AsyncMock(side_effect=exc)
    monkeypatch.setattr(audio_sources, "recording", recording)
    job = await jobs.enqueue(job_db, JobCreate(type="audio", payload=data.model_dump()))
    assert await run_once(job_db, settings=audio_settings)
    failed = await worker_read(job_db, job)
    assert failed.status == "queued" and failed.error == "handler_failed" and failed.attempts == 1
    assert not await repository.cached(job_db, decode_rid(data.lexeme_id, "lexeme"), "US")
    recording.side_effect = None
    recording.return_value = audio_sources.AudioContent(
        b"source", "audio/ogg", "wiktionary", "credits"
    )
    await make_due(job_db, job)
    assert await run_once(job_db, settings=audio_settings)
    assert (await worker_read(job_db, job)).status == "done"


async def test_cache_without_ipa_and_private_media_cannot_poison_shared_pronunciation(
    job_db: AsyncWsSurrealConnection,
    lexicon_reader: LexiconReader,
    audio_settings: Settings,
) -> None:
    result = await dictionary.materialize_lemma(job_db, lexicon_reader, "run", selected_senses=[])
    data = AudioJobPayload(
        lemma_key=["en", "run"],
        lemma_id=result.lemma_id,
        lexeme_id=result.lexeme_ids[0],
        accent="UK",
    )
    target = decode_rid(data.lexeme_id, "lexeme")
    private = await media.store(
        job_db,
        audio_settings,
        MediaCreate(
            target=target,
            owner=user_subject("private_owner"),
            kind="audio",
            mime="audio/mpeg",
            source="edge_tts",
            accent="UK",
        ),
        b"private",
    )
    assert not await repository.cached(job_db, target, "UK")
    with pytest.raises(ValueError):
        await repository.attach(job_db, target, "UK", decode_rid(private.id, "media"))
    shared = await media.store(
        job_db,
        audio_settings,
        MediaCreate(target=target, kind="audio", mime="audio/mpeg", source="edge_tts", accent="UK"),
        b"shared",
    )
    await audio.acquire(
        job_db,
        audio_settings.model_copy(update={"audio_network_enabled": False}),
        lexicon_reader,
        data,
    )
    entry = await dictionary.read_entry(job_db, user_subject("another_user"), data.lemma_id)
    assert entry is not None
    pron = next(
        item.lexeme.fields["pron"] for item in entry.lexemes if item.lexeme.id == data.lexeme_id
    )
    assert pron == [{"accent": "UK", "ipa": "", "audio": shared.id}]
