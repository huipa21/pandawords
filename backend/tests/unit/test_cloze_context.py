import pytest

from app.db.exercise_cloze import SentenceContext
from app.services.cloze_context import mask


@pytest.mark.parametrize(
    "text,selected,expected",
    [
        (
            "😀 Secret: ＲＵＮ; ran, running, runner.",
            "ＲＵＮ",
            "😀 Secret: ____; ____, ____, runner.",
        ),
        ("Cafe\u0301: run then RUN.", "RUN", "Cafe\u0301: ____ then ____."),
        ("ﬃ: run and ran.", "ran", "ﬃ: ____ and ____."),
        ("A runner runs errands.", "run", None),
    ],
)
def test_original_codepoint_spans_and_repeated_inflections(
    text: str, selected: str, expected: str | None
) -> None:
    start = text.index(selected)
    result = mask(
        SentenceContext(text, ((start, start + len(selected)),)), ("run", "ran", "running")
    )
    assert (result[0] if result else None) == expected


def test_combining_forms_multiword_and_expansions() -> None:
    text = "😀 CAFE\u0301 then CAFÉ; take \t off, TAKE OFF."
    result = mask(SentenceContext(text, ((2, 7),)), ("café", "take off"))
    assert result == ("😀 ____ then ____; ____, ____.", "CAFE\u0301")
    assert mask(SentenceContext("ß", ((0, 1),)), ("s",)) is None


@pytest.mark.parametrize("spans", [(), ((-1, 3),), ((0, 9),), ((0, 2),), ((0, 3), (2, 3))])
def test_stale_missing_or_overlapping_spans_fail_closed(spans: tuple[tuple[int, int], ...]) -> None:
    assert mask(SentenceContext("run", spans), ("run",)) is None
