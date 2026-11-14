from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.domain.dictionary import DictionaryTable
from app.domain.overrides import Text

type NoteKind = Literal["note", "mnemonic"]
type NoteText = Annotated[Text, StringConstraints(strip_whitespace=True, min_length=1)]


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_table: DictionaryTable
    target_id: str
    kind: NoteKind = "note"
    text: NoteText


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: NoteKind | None = None
    text: NoteText | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> Self:
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Note fields cannot be null.")
        return self


class NoteRead(BaseModel):
    id: str
    target_table: DictionaryTable
    target_id: str
    kind: NoteKind
    text: str
