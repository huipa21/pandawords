from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

from app.domain.dictionary import DictionaryRecordRead

TreeTable = Literal["lemma", "lexeme", "sense"]


class ProjectVisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hidden: StrictBool


class ProjectMembershipRead(BaseModel):
    id: str
    target_id: str
    hidden: bool
    added_at: datetime


class ProjectTreeSenseRead(BaseModel):
    sense: DictionaryRecordRead
    hidden: bool
    effective_hidden: bool


class ProjectTreeLexemeRead(BaseModel):
    lexeme: DictionaryRecordRead
    hidden: bool
    effective_hidden: bool
    senses: list[ProjectTreeSenseRead]


class ProjectTreeLemmaRead(BaseModel):
    lemma: DictionaryRecordRead
    hidden: bool
    effective_hidden: bool
    lexemes: list[ProjectTreeLexemeRead]


class ProjectTreePage(BaseModel):
    items: list[ProjectTreeLemmaRead]
    total: int
    page: int
    page_size: int
