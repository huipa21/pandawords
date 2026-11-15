"""Shared bundle field types and typed edge entries (one model per dictionary relation)."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
)

from app.domain.bundle_refs import REF_PATTERN, parse_ref


def _valid_ref(value: str) -> str:
    parse_ref(value)
    return value


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


type Ref = Annotated[str, Field(pattern=REF_PATTERN), AfterValidator(_valid_ref)]
type Scope = Literal["shared", "owned"]
type Text = Annotated[str, Field(max_length=100_000)]
type Short = Annotated[str, Field(min_length=1, max_length=512)]
type Lang = Annotated[str, Field(pattern=r"^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{1,8})*$")]
type Int = Annotated[int, Field(ge=-(2**63), lt=2**63)]
type NonNegative = Annotated[int, Field(ge=0, lt=2**63)]
type KeyPart = Annotated[str, Field(min_length=1, max_length=512)] | Int
type Instant = Annotated[
    AwareDatetime, AfterValidator(_utc), PlainSerializer(_iso, return_type=str, when_used="json")
]


class Entry(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, populate_by_name=True, allow_inf_nan=False
    )


class _Edge(Entry):
    owner: Scope
    from_: Ref = Field(alias="from")
    to: Ref
    # Trailing components of a shared edge's deterministic ID ``[from, to, *identity]``.
    identity: Annotated[list[KeyPart], Field(max_length=8)] = []


class HasLexemeEdge(_Edge):
    table: Literal["has_lexeme"]


class HasSenseEdge(_Edge):
    table: Literal["has_sense"]
    rank: Int


class ComposedOfEdge(_Edge):
    table: Literal["composed_of"]
    order: Int
    source: Short | None = None


class DerivesToEdge(_Edge):
    table: Literal["derives_to"]
    via: Short | None = None
    source: Short | None = None


class RelatesToEdge(_Edge):
    table: Literal["relates_to"]
    type: Literal[
        "synonym", "antonym", "hypernym", "hyponym", "confusable", "collocation", "default"
    ]
    source: Short


class MemberOfEdge(_Edge):
    table: Literal["member_of"]
    source: Short | None = None


class ContainsEdge(_Edge):
    table: Literal["contains"]
    position: NonNegative


class UsedInEdge(_Edge):
    table: Literal["used_in"]
    span: Annotated[list[NonNegative], Field(min_length=2, max_length=2)] | None = None


class PartOfEdge(_Edge):
    table: Literal["part_of"]
    order: NonNegative


type EdgeEntry = Annotated[
    HasLexemeEdge
    | HasSenseEdge
    | ComposedOfEdge
    | DerivesToEdge
    | RelatesToEdge
    | MemberOfEdge
    | ContainsEdge
    | UsedInEdge
    | PartOfEdge,
    Field(discriminator="table"),
]

EDGE_MODELS: dict[str, type[_Edge]] = {
    "has_lexeme": HasLexemeEdge,
    "has_sense": HasSenseEdge,
    "composed_of": ComposedOfEdge,
    "derives_to": DerivesToEdge,
    "relates_to": RelatesToEdge,
    "member_of": MemberOfEdge,
    "contains": ContainsEdge,
    "used_in": UsedInEdge,
    "part_of": PartOfEdge,
}

EDGE_ENDPOINTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "has_lexeme": (frozenset({"lemma"}), frozenset({"lexeme"})),
    "has_sense": (frozenset({"lexeme"}), frozenset({"sense"})),
    "composed_of": (frozenset({"lexeme"}), frozenset({"morpheme"})),
    "derives_to": (frozenset({"lexeme"}), frozenset({"lexeme"})),
    "relates_to": (frozenset({"sense"}), frozenset({"sense"})),
    "member_of": (frozenset({"sense", "morpheme", "tag"}), frozenset({"tag"})),
    "contains": (frozenset({"lemma"}), frozenset({"lexeme"})),
    "used_in": (frozenset({"sense"}), frozenset({"lemma", "sentence", "passage"})),
    "part_of": (frozenset({"sentence"}), frozenset({"passage"})),
}
