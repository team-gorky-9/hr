from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Nonempty = Annotated[str, Field(min_length=1, max_length=10000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Revision(Input):
    expected_revision: int = Field(ge=1, strict=True)


class Reason(Revision):
    reason: Nonempty


class Conditions(Input):
    starts_on: date
    ends_on: date
    time_percent: float = Field(gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on предшествует starts_on")
        return self


class OpportunityIn(Conditions):
    organization_id: UUID
    owner_actor_id: UUID
    title: Nonempty
    result_description: Nonempty


class InterestIn(Input):
    comment: str = Field(default="", max_length=10000)
