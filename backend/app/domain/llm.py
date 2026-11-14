from pydantic import BaseModel


class LlmResult[T: BaseModel](BaseModel):
    value: T
    cached: bool
