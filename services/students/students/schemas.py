from datetime import date
from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Nonempty = Annotated[str, Field(min_length=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Revision(Input):
    expected_revision: int = Field(ge=1, strict=True)


class Reason(Revision):
    reason: Nonempty


class Assignment(Revision):
    confirmation_basis: Nonempty


class OpportunityIn(Input):
    title: Nonempty
    description: Nonempty
    starts_on: date
    ends_on: date
    capacity: int = Field(ge=1, strict=True)
    mentor_actor_id: UUID

    @model_validator(mode="after")
    def dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on предшествует starts_on")
        return self


class ApplicationIn(Input):
    opportunity_id: UUID
    university_label: Nonempty
    programme_label: Nonempty
    comment: str = ""
