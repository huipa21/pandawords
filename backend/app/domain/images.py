from pydantic import BaseModel, ConfigDict, Field

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_FRAMES = 100
MAX_TOTAL_PIXELS = 50_000_000


class ImageSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")
    search_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    result_id: int = Field(gt=0)


class PixabayResult(BaseModel):
    id: int
    creator: str
    source_page: str
    attribution: str


class PixabaySearch(BaseModel):
    search_id: str
    results: list[PixabayResult]
