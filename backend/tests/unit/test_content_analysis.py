import pytest
from pydantic import ValidationError

from app.domain.content import ContentCreate, Resolution
from app.services.content_analysis import analyze, split, tokens
from app.services.lexicon import LexiconReader


@pytest.mark.parametrize(
    "text",
    [
        "  Cat! “Bird?”\n猫。🙂 Dog.",
        "e\u0301, 你好！\n\n  A final line",
        "One... Two?!\r\nThree",
        "No punctuation",
    ],
)
def test_split_preserves_original_unicode_and_whitespace(text: str) -> None:
    parts = split(text)
    assert "".join(item[0] for item in parts) == text
    for value, (start, end) in parts:
        assert text[start:end] == value


async def test_offline_occurrences_inflection_repetition_ambiguity(
    lexicon_reader: LexiconReader,
) -> None:
    text = "🙂 cats bank cats xyzunknown"
    occurrences = await analyze(lexicon_reader, text, "en")
    assert [item.text for item in occurrences] == ["cats", "bank", "cats", "xyzunknown"]
    assert all(text[item.span[0] : item.span[1]] == item.text for item in occurrences)
    assert {item.lemma for item in occurrences[0].candidates} == {"cat"}
    assert occurrences[0].candidates == occurrences[2].candidates
    assert len(occurrences[1].candidates) > 1
    assert occurrences[-1].status == "unmatched"


def test_cjk_punctuation_does_not_require_ascii_spacing() -> None:
    assert [value for value, _ in split("猫。狗！“鸟？”")] == ["猫。", "狗！", "“鸟？”"]


def test_tokens_preserve_decomposed_unicode_spans() -> None:
    assert tokens("🙂 cafe\u0301, coo\u0308perate!") == [
        ("cafe\u0301", (2, 7)),
        ("coo\u0308perate", (9, 19)),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": " "},
        {"text": "a\x00b"},
        {"text": 12},
        {"text": "a", "lang": "EN"},
        {"text": "a", "owner": "other"},
        {"text": "a", "translation": {"zh": 1}},
        {"text": "a", "translation": {"bad key": "x"}},
        {"text": "a " * 2001},
    ],
)
def test_content_strict_validation(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ContentCreate.model_validate(body)


@pytest.mark.parametrize("span", [[True, 2], ["0", 2], [1], [1, 2, 3], [0.0, 2]])
def test_span_requires_exactly_two_integers(span: list[object]) -> None:
    with pytest.raises(ValidationError):
        Resolution.model_validate({"span": span, "sense_id": "opaque"})
