"""Acquire optional shared pronunciation audio outside the add-word request."""

import asyncio
from collections import defaultdict
from typing import cast

import httpx
import structlog
from surrealdb import AsyncSurrealConnection

from app.core.config import Settings
from app.core.record_ids import decode_rid
from app.db import audio as repository
from app.domain.add_to_project import AudioJobPayload
from app.domain.dictionary_keys import DictionaryKey, lemma_key
from app.domain.media import MediaCreate
from app.services import audio_sources, media
from app.services.lexicon import LexiconReader

_locks: defaultdict[tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)


async def acquire(
    db: AsyncSurrealConnection,
    settings: Settings,
    reader: LexiconReader,
    payload: AudioJobPayload,
) -> None:
    lemma = decode_rid(payload.lemma_id, "lemma")
    lexeme = decode_rid(payload.lexeme_id, "lexeme")
    if (
        len(payload.lemma_key) != 2
        or payload.lemma_key != lemma_key("en", str(payload.lemma_key[-1]))
        or lemma.id != payload.lemma_key
        or not isinstance(lexeme.id, list)
        or lexeme.id[:2] != payload.lemma_key
        or not await repository.shared_target(db, lemma, lexeme)
    ):
        raise ValueError("Invalid shared audio job identity")
    async with _locks[(payload.lexeme_id, payload.accent)]:
        for cached in await repository.cached(db, lexeme, payload.accent):
            if await media.content_exists(settings, cached):
                await repository.attach(db, lexeme, payload.accent, cached.id)
                structlog.get_logger().info("audio_cache_hit", accent=payload.accent)
                return
        if not settings.audio_network_enabled or not settings.audio_provider_order:
            structlog.get_logger().info("audio_unavailable", reason="network_disabled")
            return
        lemma_source = await reader.get_lemma_by_id(payload.lemma_key)
        if lemma_source is None:
            raise ValueError("Audio lemma missing from lexicon")
        content: audio_sources.AudioContent | None = None
        transient: Exception | None = None
        if "wiktionary" in settings.audio_provider_order:
            pronunciations = await reader.pronunciations(cast(DictionaryKey, lexeme.id))
            async with httpx.AsyncClient(
                timeout=settings.audio_timeout_seconds, follow_redirects=False
            ) as client:
                for pron in pronunciations:
                    if pron.accent != payload.accent or pron.source != "wiktionary":
                        continue
                    try:
                        content = await audio_sources.recording(settings, pron, client)
                        break
                    except audio_sources.AudioUnavailable as exc:
                        audio_sources.unavailable(exc, accent=payload.accent, provider="wiktionary")
                    except httpx.TransportError as exc:
                        transient = exc
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429 or exc.response.status_code >= 500:
                            transient = exc
                        else:
                            audio_sources.unavailable(
                                audio_sources.AudioUnavailable("recording_http_rejected"),
                                accent=payload.accent,
                                provider="wiktionary",
                            )
        # A transient source outage retries rather than permanently caching synthetic audio.
        if content is None and transient is not None:
            raise transient
        if content is None and "edge-tts" in settings.audio_provider_order:
            voice = (
                settings.edge_tts_voice_us if payload.accent == "US" else settings.edge_tts_voice_uk
            )
            try:
                content = await audio_sources.synthesize(settings, lemma_source.text, voice)
            except audio_sources.AudioUnavailable as exc:
                audio_sources.unavailable(exc, accent=payload.accent, provider="edge_tts")
        if content is None:
            structlog.get_logger().info("audio_unavailable", accent=payload.accent)
            return
        stored = await media.store(
            db,
            settings,
            MediaCreate(
                target=lexeme,
                owner=None,
                kind="audio",
                mime=content.mime,
                source=content.source,
                attribution=content.attribution,
                accent=payload.accent,
            ),
            content.content,
        )
        await repository.attach(db, lexeme, payload.accent, decode_rid(stored.id, "media"))
