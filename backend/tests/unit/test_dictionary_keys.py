import pytest

from app.domain.dictionary_keys import lemma_key, lexeme_key, sense_key


def test_normalized_dictionary_identity() -> None:
    assert lemma_key(" EN ", " ＫＩＣＫ\t the  Bucket ") == ["en", "kick the bucket"]
    assert lemma_key("de", "STRASSE") == lemma_key("DE", "Straße")
    assert lemma_key("fr", "café") == lemma_key("fr", "cafe\u0301")
    assert lexeme_key(" EN ", "ＲＵＮ", " Verb ") == ["en", "run", "verb", 1]


def test_identity_keeps_language_pos_and_etymology_distinct() -> None:
    assert lemma_key("en", "chat") != lemma_key("fr", "chat")
    assert lexeme_key("en", "run", "verb") != lexeme_key("en", "run", "noun")
    assert lexeme_key("en", "lie", "verb", 1) != lexeme_key("en", "lie", "verb", 2)


def test_gloss_hash_is_normalized_and_uses_documented_sha1_prefix() -> None:
    assert sense_key("en", "greet", "verb", gloss=" ＨＥＬＬＯ ") == [
        "en",
        "greet",
        "verb",
        1,
        "aaf4c61ddcc5",
    ]
    assert sense_key(" EN ", "ＲＵＮ", " Verb ", gloss=" Move\tquickly ") == sense_key(
        "en", "run", "verb", gloss="move quickly"
    )
    assert sense_key("en", "run", "verb", gloss="move quickly") != sense_key(
        "en", "run", "verb", gloss="manage a business"
    )


def test_source_sense_identity_is_opaque_and_preferred_over_gloss() -> None:
    key = sense_key("en", "run", "verb", source_sense_id="Source:A", gloss="old")
    assert key[-1] == "Source:A"
    assert key == sense_key("en", "run", "verb", source_sense_id="Source:A", gloss="edited")
    assert key != sense_key("en", "run", "verb", source_sense_id="Source:a")
    assert key != sense_key("en", "run", "verb", 2, source_sense_id="Source:A")
    assert key != sense_key("en", "run", "noun", source_sense_id="Source:A")


@pytest.mark.parametrize("etymology", [0, -1, True, 1.5])
def test_reject_invalid_etymology(etymology: int) -> None:
    with pytest.raises(ValueError):
        lexeme_key("en", "run", "verb", etymology)


@pytest.mark.parametrize(
    "lang,text,pos", [("", "run", "verb"), ("en", " ", "verb"), ("en", "run", "")]
)
def test_reject_blank_identity_components(lang: str, text: str, pos: str) -> None:
    with pytest.raises(ValueError):
        lexeme_key(lang, text, pos)


@pytest.mark.parametrize("source_id,gloss", [(None, None), (None, " "), ("", None)])
def test_require_nonblank_sense_identity(source_id: str | None, gloss: str | None) -> None:
    with pytest.raises(ValueError):
        sense_key("en", "run", "verb", source_sense_id=source_id, gloss=gloss)
