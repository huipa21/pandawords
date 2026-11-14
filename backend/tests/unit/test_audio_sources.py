from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.lexicon import LexiconPronunciation
from app.services import audio_sources as sources


def configured(**values: Any) -> Settings:
    options: dict[str, Any] = {"_env_file": None, **values}
    return Settings(**options)


def pronunciation(**audio: str) -> LexiconPronunciation:
    return LexiconPronunciation(
        id="recording",
        lexeme_id=["en", "schedule", "noun", 1],
        accent="US",
        ipa=None,
        audio={key: value for key, value in audio.items()},
        tags=["US"],
        source="wiktionary",
    )


def information(url: str = "https://upload.wikimedia.org/wikipedia/commons/a/ab/En-us.ogg"):
    return {
        "query": {
            "pages": {
                "1": {
                    "imageinfo": [
                        {
                            "url": url,
                            "mime": "audio/ogg",
                            "extmetadata": {
                                "Artist": {"value": "<a href='user'>Speaker</a>"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by-sa/4.0"
                                },
                            },
                        }
                    ],
                },
            },
        },
    }


@pytest.mark.parametrize("use_url", [False, True])
async def test_recording_download_metadata_user_agent_and_throttle(
    use_url: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = configured(wikimedia_user_agent="PandaWords/test (contact@example.org)")
    requests: list[httpx.Request] = []
    throttle = AsyncMock()
    monkeypatch.setattr(sources, "_throttle", throttle)

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "commons.wikimedia.org":
            assert request.url.params["titles"] == "File:En-us.ogg"
            return httpx.Response(200, json=information())
        return httpx.Response(200, content=b"OggSrecording", headers={"content-type": "audio/ogg"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        pron = (
            pronunciation(ogg_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/En-us.ogg")
            if use_url
            else pronunciation(audio="En-us.ogg")
        )
        result = await sources.recording(settings, pron, client)
    assert result.content == b"OggSrecording"
    assert result.source == "wiktionary"
    assert result.mime == "audio/ogg"
    assert "Speaker" in result.attribution and "CC BY-SA 4.0" in result.attribution
    assert "<a" not in result.attribution
    assert all(
        request.headers["User-Agent"] == settings.wikimedia_user_agent for request in requests
    )
    assert throttle.await_count == 2


@pytest.mark.parametrize("mode", ["missing", "host", "redirect", "mime", "large", "empty"])
async def test_recordings_reject_unavailable_unsafe_and_unbounded_downloads(mode: str) -> None:
    settings = configured(audio_max_bytes=4)

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.host == "commons.wikimedia.org":
            if mode == "missing":
                return httpx.Response(200, json={"query": {"pages": {"-1": {"missing": ""}}}})
            return httpx.Response(
                200,
                json=information(
                    "http://127.0.0.1/private"
                    if mode == "host"
                    else "https://upload.wikimedia.org/wikipedia/commons/a/ab/En-us.ogg"
                ),
            )
        if mode == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        return httpx.Response(
            200,
            content=b"" if mode == "empty" else b"12345",
            headers={"content-type": "text/html" if mode == "mime" else "audio/ogg"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(
            httpx.HTTPStatusError if mode == "redirect" else sources.AudioUnavailable
        ):
            await sources.recording(settings, pronunciation(audio="En-us.ogg"), client)


async def test_real_throttle_spacing(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([10.0, 10.0, 10.1, 10.5])
    monkeypatch.setattr(sources, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(sources, "_last_request", 0.0)
    sleep = AsyncMock()
    monkeypatch.setattr(sources.asyncio, "sleep", sleep)
    settings = configured()
    await sources._throttle(settings)
    await sources._throttle(settings)
    sleep.assert_awaited_once()
    assert sleep.call_args is not None
    assert sleep.call_args.args[0] == pytest.approx(0.4)


async def test_tts_stream_uses_configured_voice_and_enforces_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[tuple[str, str]] = []

    class Speech:
        def __init__(self, text: str, voice: str) -> None:
            received.append((text, voice))

        async def stream(self) -> AsyncIterator[dict[str, object]]:
            yield {"type": "SentenceBoundary", "text": "schedule"}
            yield {"type": "audio", "data": b"MP3"}

    monkeypatch.setattr(sources.edge_tts, "Communicate", Speech)
    settings = configured()
    result = await sources.synthesize(settings, "schedule", "en-GB-SoniaNeural")
    assert received == [("schedule", "en-GB-SoniaNeural")]
    assert result.content == b"MP3" and result.source == "edge_tts"
    assert "en-GB-SoniaNeural" in result.attribution
    with pytest.raises(sources.AudioUnavailable, match="tts_too_large"):
        await sources.synthesize(
            settings.model_copy(update={"audio_max_bytes": 2}), "word", "voice"
        )
    with pytest.raises(sources.AudioUnavailable, match="tts_voice_missing"):
        await sources.synthesize(settings, "word", "")


@pytest.mark.parametrize("no_audio_error", [False, True])
async def test_tts_no_audio_is_explicitly_unavailable(
    no_audio_error: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Speech:
        def __init__(self, text: str, voice: str) -> None:
            pass

        async def stream(self) -> AsyncIterator[dict[str, object]]:
            if no_audio_error:
                raise sources.edge_tts.exceptions.NoAudioReceived("no data")
            yield {"type": "SentenceBoundary", "text": "word"}

    monkeypatch.setattr(sources.edge_tts, "Communicate", Speech)
    with pytest.raises(sources.AudioUnavailable, match="tts_no_audio"):
        await sources.synthesize(configured(), "word", "voice")


@pytest.mark.parametrize(
    "update",
    [
        {"audio_provider_order": "edge-tts,wiktionary"},
        {"audio_provider_order": "unknown"},
        {"wikimedia_request_interval_seconds": 0.1},
        {"wikimedia_user_agent": "bad\nheader"},
    ],
)
def test_audio_settings_guard_fetch_etiquette(update: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        configured(**update)
