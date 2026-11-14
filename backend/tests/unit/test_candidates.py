import asyncio
import threading
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from spacy.language import Language

from app.domain.candidates import CandidateRequest
from app.services import candidates
from app.services.candidates import CandidateService
from app.services.lexicon import LexiconReader


@pytest.mark.parametrize(
    ("text", "normalized", "lemma"),
    [
        ("  ＲＵＮ  ", "run", "run"),
        ("RAN", "ran", "run"),
        ("children", "children", "child"),
        (" Give\t UP ", "give up", "give up"),
        ("kicked the bucket", "kicked the bucket", "kick the bucket"),
    ],
)
async def test_exact_inflected_and_phrase(
    lexicon_reader: LexiconReader, text: str, normalized: str, lemma: str
) -> None:
    result = await CandidateService(lexicon_reader).resolve(CandidateRequest(text=text))
    assert result.normalized == normalized
    assert [candidate.lemma.text for candidate in result.candidates] == [lemma]
    assert all(lexeme.senses for lexeme in result.candidates[0].lexemes)
    if normalized == "run":
        assert "exact" in result.candidates[0].matched_by
        verb = next(item for item in result.candidates[0].lexemes if item.lexeme.pos == "verb")
        assert [sense.common for sense in verb.senses] == [True, True, False]
        assert verb.senses[0].gloss_zh == "跑"
        assert verb.senses[0].source_id == "run-move"
        assert verb.glosses
        assert {"wiktionary", "ecdict", "wordfreq"} <= {source.name for source in result.sources}


@pytest.mark.parametrize("text", ["", " \t\n ", "!!!", "123", "run\x00", "run\u200b", "x" * 201])
def test_invalid_input(text: str) -> None:
    with pytest.raises(ValidationError):
        CandidateRequest(text=text)


@pytest.mark.parametrize("text", ["zzqxyunknown", "unknown phrase"])
async def test_unknown(lexicon_reader: LexiconReader, text: str) -> None:
    result = await CandidateService(lexicon_reader).resolve(CandidateRequest(text=text))
    assert result.candidates == [] and result.sources == []


async def test_multiple_candidates_are_deduplicated(lexicon_reader: LexiconReader) -> None:
    run = await lexicon_reader.get_lemma("run")
    bank = await lexicon_reader.get_lemma("bank")
    assert run is not None and bank is not None
    with patch.object(lexicon_reader, "lookup_form", AsyncMock(return_value=[run, bank, run])):
        result = await CandidateService(lexicon_reader).resolve(CandidateRequest(text="run"))
    assert [item.lemma.text for item in result.candidates] == ["run", "bank"]
    assert result.candidates[0].matched_by == ["exact", "form"]
    assert len(result.candidates[1].lexemes) == 2
    assert [item.lexeme.etymology_no for item in result.candidates[1].lexemes] == [1, 2]


async def test_spacy_initialization_and_inference_are_off_loop(
    lexicon_reader: LexiconReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_thread = threading.get_ident()
    observed: list[int] = []
    real_pipeline = candidates._pipeline
    real_pipeline.cache_clear()

    def checked_pipeline() -> Language:
        observed.append(threading.get_ident())
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return real_pipeline()

    monkeypatch.setattr(candidates, "_pipeline", checked_pipeline)
    # "walks" is absent from fixture form_index: only spaCy lookup resolves it.
    assert await lexicon_reader.lookup_form("walks") == []
    result = await CandidateService(lexicon_reader).resolve(CandidateRequest(text="walks"))
    assert [item.lemma.text for item in result.candidates] == ["walk"]
    assert result.candidates[0].matched_by == ["spacy"]
    assert observed and all(thread != loop_thread for thread in observed)
