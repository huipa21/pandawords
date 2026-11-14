import random

import pytest

from app.domain.distractors import DistractorPool, DistractorRecord
from app.domain.exercises import DistractorCandidates, Unavailable
from app.services.distractors import frequency_band, select_choices


def record(name: str, tier: int = 0, **changes: object) -> DistractorRecord:
    return DistractorRecord.model_validate(
        {
            "sense_id": name,
            "word": name,
            "definition": f"definition {name}",
            "pos": "noun",
            "freq_zipf": 4.5,
            "tier": tier,
            **changes,
        }
    )


def pool(
    *candidates: DistractorRecord, synonyms: tuple[DistractorRecord, ...] = ()
) -> DistractorPool:
    return DistractorPool(answer=record("answer"), candidates=candidates, synonyms=synonyms)


def ids(result: DistractorCandidates | Unavailable) -> set[str]:
    assert isinstance(result, DistractorCandidates)
    return {choice.id for choice in result.choices}


@pytest.mark.parametrize("tier", range(4))
def test_each_tier_works_independently(tier: int) -> None:
    assert ids(select_choices(pool(record("candidate", tier)))) == {"answer", "candidate"}


def test_rank_priority_and_reproducibility() -> None:
    candidates = [record(f"tier{tier}", tier) for tier in reversed(range(4))]
    result = select_choices(pool(*candidates), rng=random.Random(23))
    assert ids(result) == {"answer", "tier0", "tier1", "tier2"}
    assert result == select_choices(pool(*reversed(candidates)), rng=random.Random(23))
    for seed in range(10):
        assert ids(select_choices(pool(*candidates), rng=random.Random(seed))) == ids(result)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (0, None),
        (-1, None),
        (float("nan"), None),
        (float("inf"), None),
        (0.01, 0),
        (3.9999, 3),
        (4.0, 4),
        (4.9999, 4),
        (5.0, 5),
    ],
)
def test_frequency_bands(value: float | None, expected: int | None) -> None:
    assert frequency_band(value) == expected


@pytest.mark.parametrize("frequency", [None, 0, 3.9999, 5.0])
def test_unknown_and_adjacent_bands_do_not_match(frequency: float | None) -> None:
    assert isinstance(select_choices(pool(record("bad", 3, freq_zipf=frequency))), Unavailable)
    unknown_answer = pool(record("candidate", 3)).model_copy(
        update={"answer": record("answer", freq_zipf=frequency)}
    )
    assert isinstance(select_choices(unknown_answer), Unavailable)


def test_missing_pos_and_no_graph_data_are_unavailable() -> None:
    assert isinstance(select_choices(pool()), Unavailable)
    assert isinstance(select_choices(pool(record("other", 3, pos="verb"))), Unavailable)
    assert isinstance(select_choices(pool(record("other", 3, pos=None))), Unavailable)
    assert isinstance(
        select_choices(
            pool(record("other", 3)).model_copy(update={"answer": record("answer", pos=None)})
        ),
        Unavailable,
    )


def test_synonym_ids_and_displayed_synonym_words_are_excluded() -> None:
    source = pool(
        record("answer"),
        record("synonym"),
        record("alias", word="SYNONYM"),
        record("safe"),
        synonyms=(record("synonym"),),
    )
    assert ids(select_choices(source)) == {"answer", "safe"}


def test_duplicate_words_definitions_unicode_and_ids() -> None:
    source = pool(
        record("a", word="  ＡＮＳＷＥＲ "),
        record("b", word="same"),
        record("c", word=" SAME "),
        record("d", definition="  DEFINITION   ANSWER "),
        record("e", definition="definition b"),
        record("b", word="alias"),
        record("blank", word=" ", definition=" "),
    )
    assert ids(select_choices(source)) == {"answer", "b", "d", "e"}
    assert ids(select_choices(source, label="definition")) == {"answer", "a", "b", "c"}


def test_answer_label_missing_and_choice_count_limits() -> None:
    source = pool(record("safe")).model_copy(update={"answer": record("answer", word=" ")})
    assert isinstance(select_choices(source), Unavailable)
    assert len(ids(select_choices(pool(record("safe"))))) == 2
    for count in (1, 5):
        with pytest.raises(ValueError):
            select_choices(pool(record("safe")), count=count)
