import base64
import re
from typing import cast
from uuid import uuid4

import pytest
from surrealdb import RecordID

from app.core.record_ids import decode_rid, encode_rid
from app.domain.dictionary_keys import lemma_key, lexeme_key, sense_key
from app.domain.identity import user_key, user_subject


def _token(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "record",
    [
        RecordID("lemma", lemma_key("en", "kick the bucket")),
        RecordID("lexeme", lexeme_key("en", "run", "verb")),
        RecordID("sense", sense_key("en", "run", "verb", gloss="move quickly")),
        RecordID("user", "abc_123"),
        RecordID("user", ""),
        RecordID("tag", "123"),
        RecordID("tag", "123abc"),
        RecordID("tag", "two words:中文/é'\"\\\n"),
        RecordID("tag", 123),
        RecordID("tag", -(2**63)),
        RecordID("tag", 2**63 - 1),
        RecordID("tag", []),
        RecordID("tag", {}),
        RecordID("tag", {"z": [True, None, -1.5], "a": {"b": "null"}}),
        RecordID(
            "override",
            [
                RecordID("user", "abc"),
                RecordID("sense", ["en", "run", "verb", 1, "source:1"]),
            ],
        ),
        RecordID("tag", {"target": RecordID("lemma", ["en", "run"])}),
    ],
)
def test_round_trip_preserves_structured_keys(record: RecordID) -> None:
    token = encode_rid(record, record.table_name)
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)
    decoded = decode_rid(token, record.table_name)
    assert decoded == record
    assert type(decoded.id) is type(record.id)
    assert encode_rid(decoded, record.table_name) == token


def test_record_key_types_do_not_collide() -> None:
    records = [RecordID("tag", key) for key in ["123", 123, "[1]", [1], '{"x":1}', {"x": 1}]]
    assert len({encode_rid(record, "tag") for record in records}) == len(records)


def test_object_order_is_canonical_and_auth_helper_remains_compatible() -> None:
    assert encode_rid(RecordID("tag", {"b": 2, "a": 1}), "tag") == encode_rid(
        RecordID("tag", {"a": 1, "b": 2}), "tag"
    )
    subject = user_subject("abc_123")
    assert subject == encode_rid(RecordID("user", "abc_123"), "user")
    assert user_key(subject) == decode_rid(subject, "user").id


@pytest.mark.parametrize(
    "text",
    [
        "",
        "lemma",
        "lemma:",
        "lemma:[",
        'lemma:["en","run",]',
        'lemma:{"a":1,"a":2}',
        "lemma:1;DELETE user",
        "lemma:1 trailing",
        "lemma:1.0",
        "lemma:[NaN]",
        "lemma:9223372036854775808",
        'lemma:{"x":Infinity}',
        'lemma:[__import__("os")]',
        'lemma: {"a":1}',
        "bad-table:abc",
    ],
)
def test_reject_malformed_record_text(text: str) -> None:
    with pytest.raises(ValueError):
        decode_rid(_token(text), "lemma")


@pytest.mark.parametrize("token", ["", "=", "abc+", "abc/", "a", "____", "A" * 16385])
def test_reject_invalid_base64url(token: str) -> None:
    with pytest.raises(ValueError):
        decode_rid(token, "lemma")


def test_reject_padding_and_noncanonical_pad_bits() -> None:
    token = encode_rid(RecordID("tag", 1), "tag")
    assert token == "dGFnOjE"
    for invalid in [token + "=", token[:-1] + "F"]:
        with pytest.raises(ValueError):
            decode_rid(invalid, "tag")


def test_validate_expected_table_in_both_directions() -> None:
    record = RecordID("user", "abc")
    with pytest.raises(ValueError):
        encode_rid(record, "lemma")
    with pytest.raises(ValueError):
        decode_rid(encode_rid(record, "user"), "lemma")
    with pytest.raises(ValueError):
        decode_rid(_token("lemma:abc"), "")


@pytest.mark.parametrize("key", [uuid4(), ("en", "run"), 2**63, {"bad": float("inf")}])
def test_reject_unsupported_record_values(key: object) -> None:
    # Constructor accepts more SDK key types than this transport's documented subset.
    record = RecordID("tag", "placeholder")
    record.id = cast(str, key)
    with pytest.raises(ValueError):
        encode_rid(record, "tag")


def test_reject_excessive_depth_size_and_cycles() -> None:
    record = RecordID("tag", ["x"])
    for _ in range(40):
        record = RecordID("tag", [record])
    with pytest.raises(ValueError):
        encode_rid(record, "tag")
    with pytest.raises(ValueError):
        decode_rid(_token("tag:" + "[" * 40 + "1" + "]" * 40), "tag")
    with pytest.raises(ValueError):
        encode_rid(RecordID("tag", "x" * 13000), "tag")
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(ValueError):
        encode_rid(RecordID("tag", cycle), "tag")
