"""Public, ownership-free graph transport."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.dictionary import DictionaryRelation, DictionaryTable

type GraphDirection = Literal["both", "outgoing", "incoming"]


class GraphSeedsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(default="", max_length=200)
    project_id: str | None = Field(default=None, max_length=16384)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=100)
    node_types: list[DictionaryTable] = Field(default_factory=list, max_length=7)


class GraphQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_id: str = Field(min_length=1, max_length=16384)
    depth: int = Field(default=1, ge=0, le=3)
    node_types: list[DictionaryTable] = Field(default_factory=list, max_length=7)
    relation_types: list[DictionaryRelation] = Field(default_factory=list, max_length=9)
    direction: GraphDirection = "both"


class GraphForm(BaseModel):
    form: str
    tags: list[str]


class GraphPronunciation(BaseModel):
    accent: Literal["US", "UK"]
    ipa: str
    audio: str | None = None


class GraphFrequency(BaseModel):
    source: str
    zipf: float | None = None
    bnc: int | None = None
    coca: int | None = None


class GraphExamSource(BaseModel):
    tag: str
    source: str


class LemmaFields(BaseModel):
    text: str
    lang: str
    kind: Literal["word", "phrase"]
    freq_zipf: float
    cefr: str | None = None
    exam_tags: list[str]
    source: str
    frequencies: list[GraphFrequency] | None = None
    exam_tag_sources: list[GraphExamSource] | None = None


class LexemeFields(BaseModel):
    pos: str
    etymology_no: int
    etymology_text: str | None = None
    forms: list[GraphForm]
    pron: list[GraphPronunciation]


class SenseFields(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    definition: str
    gloss: dict[str, str]
    register_: list[str] = Field(alias="register")
    domain: list[str]
    examples: list[str]
    rank: int
    common: bool
    source: str


class MorphemeFields(BaseModel):
    text: str
    type: Literal["prefix", "root", "suffix", "infix"]
    meaning: str | None = None


class TagFields(BaseModel):
    kind: str
    name: str


class SentenceFields(BaseModel):
    text: str
    lang: str
    translation: dict[str, str]
    source: str


class PassageFields(BaseModel):
    title: str
    text: str
    lang: str
    source: str


class LemmaNode(BaseModel):
    id: str
    table: Literal["lemma"]
    fields: LemmaFields


class LexemeNode(BaseModel):
    id: str
    table: Literal["lexeme"]
    fields: LexemeFields


class SenseNode(BaseModel):
    id: str
    table: Literal["sense"]
    fields: SenseFields


class MorphemeNode(BaseModel):
    id: str
    table: Literal["morpheme"]
    fields: MorphemeFields


class TagNode(BaseModel):
    id: str
    table: Literal["tag"]
    fields: TagFields


class SentenceNode(BaseModel):
    id: str
    table: Literal["sentence"]
    fields: SentenceFields


class PassageNode(BaseModel):
    id: str
    table: Literal["passage"]
    fields: PassageFields


type GraphNode = Annotated[
    LemmaNode | LexemeNode | SenseNode | MorphemeNode | TagNode | SentenceNode | PassageNode,
    Field(discriminator="table"),
]


class GraphEdgeFields(BaseModel):
    rank: int | None = None
    order: int | None = None
    position: int | None = None
    via: str | None = None
    type: (
        Literal["synonym", "antonym", "hypernym", "hyponym", "confusable", "collocation", "default"]
        | None
    ) = None
    source: str | None = None
    span: tuple[int, int] | None = None


class GraphEdge(BaseModel):
    id: str
    table: DictionaryRelation
    start: str
    end: str
    fields: GraphEdgeFields


class GraphRead(BaseModel):
    focus_id: str
    depth: int
    direction: GraphDirection
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_types: list[DictionaryTable]
    relation_types: list[DictionaryRelation]
    node_limit: Literal[300] = 300
