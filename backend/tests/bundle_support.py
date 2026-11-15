"""Repository-shaped rows covering every bundle record/edge category (unit-test fixture)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from surrealdb import RecordID

from app.domain.bundle_manifest import ManifestHeader
from app.domain.bundle_serialize import BundleSource

OWNER = RecordID("user", "alice-secret-id")
T0 = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nfixture-image"
AUDIO_BYTES = b"ID3fixture-audio"

LEMMA = RecordID("lemma", ["en", "run"])
PHRASE = RecordID("lemma", ["en", "run out"])
LEXEME = RecordID("lexeme", ["en", "run", "verb", 1])
LEXEME_NOUN = RecordID("lexeme", ["en", "run", "noun", 1])
SENSE = RecordID("sense", ["en", "run", "verb", 1, "s1"])
SENSE_2 = RecordID("sense", ["en", "run", "verb", 1, "s2"])
MORPHEME = RecordID("morpheme", ["en", "re-", "prefix", 1])
TAG = RecordID("tag", ["domain", "sport"])
OWN_SENSE = RecordID("sense", "own-sense-q1")
OWN_TAG = RecordID("tag", "own-tag-z9")
OWN_SENTENCE = RecordID("sentence", "own-sentence-k3")
OWN_PASSAGE = RecordID("passage", "own-passage-p7")
PROJECT = RecordID("project", "project-x4")
NOTE = RecordID("note", "note-n2")
IMAGE = RecordID("media", "media-img-7")
AUDIO = RecordID("media", "media-audio-shared")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _shared(record: RecordID, **fields: Any) -> dict[str, Any]:
    return {"id": record, **fields}


def _owned(record: RecordID, **fields: Any) -> dict[str, Any]:
    return {"id": record, "owner": OWNER, **fields}


def _edge(table: str, start: RecordID, end: RecordID, *identity: Any, **fields: Any) -> dict:
    owner = fields.pop("owner", None)
    key = [start, end, *identity] if owner is None else f"{table}-{len(fields)}-{end.id}"
    row = {"id": RecordID(table, key), "in": start, "out": end, **fields}
    return row | ({"owner": owner} if owner is not None else {})


def records() -> list[dict[str, Any]]:
    return [
        _shared(
            LEMMA,
            text="run",
            lang="en",
            kind="word",
            freq_zipf=5.5,
            cefr="A1",
            exam_tags=["cet4"],
            source="wiktionary",
            frequencies=[{"source": "wordfreq", "zipf": 5.5}],
            exam_tag_sources=[{"tag": "cet4", "source": "ecdict"}],
        ),
        _shared(
            PHRASE,
            text="run out",
            lang="en",
            kind="phrase",
            freq_zipf=3.0,
            exam_tags=[],
            source="wiktionary",
        ),
        _shared(
            LEXEME,
            pos="verb",
            etymology_no=1,
            etymology_text="Old English",
            forms=[{"form": "ran", "tags": ["past"]}, {"form": "running", "tags": []}],
            pron=[
                {"accent": "US", "ipa": "/rʌn/", "audio": AUDIO},
                {"accent": "UK", "ipa": "/rʌn/"},
            ],
        ),
        _shared(LEXEME_NOUN, pos="noun", etymology_no=1, forms=[], pron=[]),
        _shared(
            SENSE,
            definition="move fast",
            gloss={"zh": "跑"},
            register=[],
            domain=["sport"],
            examples=["I run."],
            rank=0,
            common=True,
            source="oewn",
        ),
        _shared(
            SENSE_2,
            definition="operate",
            gloss={},
            register=["formal"],
            domain=[],
            examples=[],
            rank=1,
            common=False,
            source="oewn",
        ),
        _shared(MORPHEME, text="re-", type="prefix", meaning="again", source="affixes"),
        _shared(TAG, kind="domain", name="sport"),
        _owned(
            OWN_SENSE,
            definition="my sense",
            gloss={"zh": "我的"},
            register=[],
            domain=[],
            examples=[],
            rank=9,
            common=False,
            source="user",
        ),
        _owned(OWN_TAG, kind="custom", name="Exam words"),
        _owned(
            OWN_SENTENCE,
            text="I run out.",
            lang="en",
            translation={"zh": "我用完了"},
            source="user",
        ),
        _owned(OWN_PASSAGE, title="Story", text="I run out.", lang="en", source="user"),
    ]


def edges() -> list[dict[str, Any]]:
    return [
        _edge("has_lexeme", LEMMA, LEXEME),
        _edge("has_lexeme", LEMMA, LEXEME_NOUN),
        _edge("has_sense", LEXEME, SENSE, rank=0),
        _edge("has_sense", LEXEME, SENSE_2, rank=1),
        _edge("composed_of", LEXEME, MORPHEME, 0, "affixes", order=0, source="affixes"),
        _edge("derives_to", LEXEME, LEXEME_NOUN, via="conversion"),
        _edge("relates_to", SENSE, SENSE_2, "synonym", "oewn", type="synonym", source="oewn"),
        _edge("member_of", SENSE, TAG),
        _edge("contains", PHRASE, LEXEME, 0, position=0),
        _edge("used_in", SENSE, PHRASE),
        _edge("has_sense", LEXEME, OWN_SENSE, rank=9, owner=OWNER),
        _edge("relates_to", OWN_SENSE, SENSE, type="confusable", source="user", owner=OWNER),
        _edge("member_of", OWN_TAG, TAG, owner=OWNER),
        _edge("member_of", SENSE, OWN_TAG, owner=OWNER),
        _edge("used_in", SENSE, OWN_SENTENCE, span=[2, 5], owner=OWNER),
        _edge("part_of", OWN_SENTENCE, OWN_PASSAGE, order=0, owner=OWNER),
    ]


def source() -> BundleSource:
    project_row = _owned(
        PROJECT,
        name="IELTS",
        description="",
        target_lang="en",
        source_lang="zh",
        plan={"daily_new": 20, "exam_date": T0, "review_cap": 100},
        created_at=T0,
        srs_revision=4,
    )
    include = {"owner": OWNER, "in": PROJECT, "added_at": T0}
    memory_id = RecordID("memory", [OWNER, SENSE])
    card = {
        "card_id": 17,
        "state": 2,
        "step": None,
        "stability": 3.5,
        "difficulty": 5.25,
        "due": T0,
        "last_review": T0,
    }
    return BundleSource(
        records=records(),
        edges=edges(),
        projects=[project_row],
        includes=[
            {
                **include,
                "id": RecordID("includes", [PROJECT, LEMMA]),
                "out": LEMMA,
                "hidden": False,
            },
            {
                **include,
                "id": RecordID("includes", [PROJECT, LEXEME]),
                "out": LEXEME,
                "hidden": True,
            },
            {
                **include,
                "id": RecordID("includes", [PROJECT, SENSE]),
                "out": SENSE,
                "hidden": False,
                "study_order": 1,
            },
            {
                **include,
                "id": RecordID("includes", [PROJECT, OWN_SENSE]),
                "out": OWN_SENSE,
                "hidden": True,
                "study_order": 0,
            },
        ],
        overrides=[
            {
                "id": RecordID("override", [OWNER, SENSE]),
                "owner": OWNER,
                "fields": {"definition": "my words", "gloss": {"zh": "奔跑"}},
                "updated_at": T0,
            },
        ],
        notes=[_owned(NOTE, target=SENSE, kind="mnemonic", text="run = 润")],
        media=[
            _owned(
                IMAGE,
                target=SENSE,
                kind="image",
                path="image/ab/secret.png",
                mime="image/png",
                source="pixabay",
                attribution="Pixabay user",
            ),
            _shared(
                AUDIO,
                target=LEXEME,
                kind="audio",
                path="audio/cd/x.mp3",
                mime="audio/mpeg",
                source="wiktionary",
                accent="US",
            ),
        ],
        memory=[
            {
                "id": memory_id,
                "owner": OWNER,
                "sense": SENSE,
                "introduced": True,
                "card_id": 17,
                "state": 2,
                "stability": 3.5,
                "difficulty": 5.25,
                "due": T0,
                "last_review": T0,
            },
        ],
        review_log=[
            {
                "id": RecordID("review_log", "log-1"),
                "owner": OWNER,
                "memory": memory_id,
                "project": PROJECT,
                "exercise": "recall",
                "rating": 3,
                "auto_rating": 3,
                "correct": True,
                "hint_used": False,
                "duration_ms": 4200,
                "at": T0,
                "is_introduction": True,
                "attempt_id": "attempt-1",
                "request_fingerprint": "f" * 64,
                "receipt": {
                    "memory": {
                        "id": "memory:secret",
                        "card": {**card, "due": T0.isoformat(), "last_review": T0.isoformat()},
                    }
                },
            },
            {
                "id": RecordID("review_log", "log-0"),
                "owner": OWNER,
                "memory": memory_id,
                "project": RecordID("project", "deleted-project"),
                "exercise": "choice",
                "rating": 1,
                "auto_rating": 2,
                "correct": False,
                "hint_used": True,
                "duration_ms": 0,
                "at": datetime(2025, 12, 1, tzinfo=UTC),
                "is_introduction": False,
                "attempt_id": "attempt-0",
            },
        ],
        user={
            "id": OWNER,
            "username": "alice",
            "password_hash": "argon2-secret",
            "role": "admin",
            "source_lang": "zh",
            "target_lang": "en",
            "tag_revision": 3,
            "prefs": {
                "theme": "dark",
                "locale": "zh-CN",
                "accent": "UK",
                "desired_retention": 0.85,
                "review_images_enabled": False,
                "review_audio_enabled": True,
            },
        },
        media_sha256={IMAGE: _sha(IMAGE_BYTES), AUDIO: _sha(AUDIO_BYTES)},
    )


def header(bundle_format: str = "pandawords.user") -> ManifestHeader:
    return ManifestHeader.model_validate(
        {
            "format": bundle_format,
            "app_version": "0.1.0",
            "created_at": T0,
            "lexicon_version": "lexicon-2026.1",
            "source_lang": "zh",
            "target_lang": "en",
            "attribution": ["Wiktionary (CC BY-SA)", "Open English WordNet (CC BY 4.0)"],
        }
    )


def media_files(root: Path) -> tuple[dict[RecordID, str], dict[str, Path]]:
    """Write fixture media bytes; returns per-media sha256 and the bundle file map."""
    shas: dict[RecordID, str] = {}
    files: dict[str, Path] = {}
    for record, data, ext in ((IMAGE, IMAGE_BYTES, ".png"), (AUDIO, AUDIO_BYTES, ".mp3")):
        sha = hashlib.sha256(data).hexdigest()
        path = root / f"{record.id}{ext}"
        path.write_bytes(data)
        shas[record] = sha
        files[f"media/{sha}{ext}"] = path
    return shas, files
