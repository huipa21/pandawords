"""Canonical structured keys for shared dictionary records."""

import hashlib
import unicodedata

type DictionaryKey = list[str | int]


def _normalized(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Identity text must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not normalized:
        raise ValueError("Identity text must not be blank")
    return normalized


def lemma_key(lang: str, text: str) -> DictionaryKey:
    return [_normalized(lang), _normalized(text)]


def lexeme_key(lang: str, text: str, pos: str, etymology_no: int = 1) -> DictionaryKey:
    if type(etymology_no) is not int or etymology_no < 1:
        raise ValueError("Etymology number must be a positive integer")
    return [*lemma_key(lang, text), _normalized(pos), etymology_no]


def sense_key(
    lang: str,
    text: str,
    pos: str,
    etymology_no: int = 1,
    *,
    source_sense_id: str | None = None,
    gloss: str | None = None,
) -> DictionaryKey:
    key = lexeme_key(lang, text, pos, etymology_no)
    if source_sense_id is not None:
        if not isinstance(source_sense_id, str) or not source_sense_id.strip():
            raise ValueError("Source sense ID must not be blank")
        identity = source_sense_id
    elif gloss is not None:
        identity = hashlib.sha1(_normalized(gloss).encode(), usedforsecurity=False).hexdigest()[:12]
    else:
        raise ValueError("A source sense ID or gloss is required")
    return [*key, identity]
