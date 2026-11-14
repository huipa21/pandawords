"""Bounded Wikimedia downloads and optional Edge speech synthesis."""

import asyncio
import html
import re
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

import edge_tts
import httpx
import structlog

from app.core.config import Settings
from app.domain.lexicon import LexiconPronunciation
from app.domain.media import MIME_EXTENSIONS, MediaSource


@dataclass(frozen=True)
class AudioContent:
    content: bytes
    mime: str
    source: MediaSource
    attribution: str


class AudioUnavailable(Exception):
    """An expected permanent absence, not a retryable worker failure."""


_request_lock = asyncio.Lock()
_last_request = 0.0


async def _throttle(settings: Settings) -> None:
    global _last_request
    async with _request_lock:
        delay = settings.wikimedia_request_interval_seconds - (time.monotonic() - _last_request)
        if delay > 0:
            await asyncio.sleep(delay)
        _last_request = time.monotonic()


def _safe_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
        return (
            parts.scheme == "https"
            and parts.hostname == "upload.wikimedia.org"
            and parts.port in (None, 443)
            and parts.username is None
            and parts.password is None
            and parts.path.startswith("/wikipedia/commons/")
        )
    except ValueError:
        return False


def _filename(pron: LexiconPronunciation) -> str | None:
    filename = pron.audio.get("audio")
    if isinstance(filename, str) and filename.strip():
        return filename.removeprefix("File:")
    for key in ("mp3_url", "ogg_url"):
        value = pron.audio.get(key)
        if isinstance(value, str) and _safe_url(value):
            parts = unquote(urlsplit(value).path).split("/")
            return parts[-2] if "/transcoded/" in value else parts[-1]
    return None


def _text(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", value)).strip()


def _check_response(response: httpx.Response) -> None:
    if response.status_code in (404, 410):
        raise AudioUnavailable("recording_missing")
    response.raise_for_status()


def _mime(value: str) -> str:
    value = value.split(";")[0].strip().lower()
    return "audio/ogg" if value == "application/ogg" else value


async def recording(
    settings: Settings, pron: LexiconPronunciation, client: httpx.AsyncClient
) -> AudioContent:
    filename = _filename(pron)
    if filename is None:
        raise AudioUnavailable("recording_missing")
    await _throttle(settings)
    response = await client.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "titles": f"File:{filename}",
        },
        headers={"User-Agent": settings.wikimedia_user_agent},
    )
    _check_response(response)
    pages = response.json().get("query", {}).get("pages", {})
    information = [info for page in pages.values() for info in page.get("imageinfo", [])]
    if not information:
        raise AudioUnavailable("recording_missing")
    info = information[0]
    url = info.get("url", "")
    mime = _mime(info.get("mime", ""))
    if not isinstance(url, str) or not _safe_url(url) or mime not in MIME_EXTENSIONS["audio"]:
        raise AudioUnavailable("recording_unsupported")
    metadata = info.get("extmetadata", {})
    credits = []
    for key in ("attribution", "author", "license", "license_url"):
        value = pron.audio.get(key)
        if isinstance(value, str) and value:
            credits.append(f"{key}: {_text(value)}")
    for key in ("Artist", "Credit", "LicenseShortName", "LicenseUrl", "Attribution"):
        value = metadata.get(key, {}).get("value")
        if isinstance(value, str) and value:
            credits.append(f"{key}: {_text(value)}")
    attribution = "\n".join([f"Wiktionary / Wikimedia Commons: File:{filename}", url, *credits])[
        :4000
    ]
    await _throttle(settings)
    content = bytearray()
    async with client.stream(
        "GET", url, headers={"User-Agent": settings.wikimedia_user_agent}
    ) as download:
        _check_response(download)
        received_mime = _mime(download.headers.get("content-type", ""))
        if received_mime != mime:
            raise AudioUnavailable("recording_content_type")
        async for chunk in download.aiter_bytes():
            content.extend(chunk)
            if len(content) > settings.audio_max_bytes:
                raise AudioUnavailable("recording_too_large")
    if not content:
        raise AudioUnavailable("recording_empty")
    return AudioContent(bytes(content), mime, "wiktionary", attribution)


async def synthesize(settings: Settings, text: str, voice: str) -> AudioContent:
    if not voice.strip():
        raise AudioUnavailable("tts_voice_missing")
    content = bytearray()
    try:
        async with asyncio.timeout(settings.audio_timeout_seconds):
            async for chunk in edge_tts.Communicate(text, voice).stream():
                if chunk["type"] == "audio":
                    data = chunk.get("data")
                    if not isinstance(data, bytes):
                        raise ValueError("Invalid Edge TTS audio chunk")
                    content.extend(data)
                    if len(content) > settings.audio_max_bytes:
                        raise AudioUnavailable("tts_too_large")
    except edge_tts.exceptions.NoAudioReceived as exc:
        raise AudioUnavailable("tts_no_audio") from exc
    if not content:
        raise AudioUnavailable("tts_no_audio")
    return AudioContent(
        bytes(content), "audio/mpeg", "edge_tts", f"Microsoft Edge TTS; voice: {voice}"
    )


def unavailable(reason: Exception, *, accent: str, provider: str) -> None:
    structlog.get_logger().info(
        "audio_provider_unavailable", accent=accent, provider=provider, reason=str(reason)
    )
