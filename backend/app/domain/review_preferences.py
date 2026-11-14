from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_images_enabled: bool = Field(default=True, strict=True)
    review_audio_enabled: bool = Field(default=True, strict=True)
    accent: Literal["US", "UK"] = "US"


class ReviewPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_images_enabled: bool | None = Field(default=None, strict=True)
    review_audio_enabled: bool | None = Field(default=None, strict=True)
    accent: Literal["US", "UK"] | None = None

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("Provide at least one non-null review preference")
        return self
