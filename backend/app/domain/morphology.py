from typing import Literal

from pydantic import BaseModel


def component_order_valid(types: list[str]) -> bool:
    roots = [index for index, kind in enumerate(types) if kind == "root"]
    if not roots:
        return False
    return all(
        kind == "root"
        or (kind == "prefix" and index < roots[0])
        or (kind == "suffix" and index > roots[-1])
        or (kind == "infix" and roots[0] < index < roots[-1])
        for index, kind in enumerate(types)
    )


class MorphemeRead(BaseModel):
    id: str
    text: str
    type: Literal["root", "prefix", "suffix", "infix"]
    meaning: str | None
    order: int
    source: str | None
    readonly: bool


class MorphGroupMemberRead(BaseModel):
    id: str
    table: Literal["sense", "morpheme"]
