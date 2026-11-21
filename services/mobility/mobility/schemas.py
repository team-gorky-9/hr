from datetime import date
from typing import Annotated, Literal
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


class ProposalIn(Conditions):
    manager_actor_id: UUID
    manager_source_reference: Nonempty


class Response(Revision):
    accepted: bool = Field(strict=True)
    reason: Nonempty | None = None


class ManagerResponse(Response):
    @model_validator(mode="after")
    def refusal_reason(self):
        if not self.accepted and not self.reason:
            raise ValueError("Отказ требует объяснения")
        return self


class ProposalPatch(Reason):
    starts_on: date | None = None
    ends_on: date | None = None
    time_percent: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def not_null(self):
        for field in ("starts_on", "ends_on", "time_percent"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("Условие не может быть null")
        return self


class Finish(Revision):
    outcome: Literal["completed", "stopped"]
    result_note: Nonempty


class Feedback(Revision):
    accepted: bool = Field(strict=True)
    note: Nonempty


class PackageIn(Input):
    purpose: Nonempty
    share_allowed: bool = Field(strict=True)


class VacancyInterestIn(InterestIn):
    vacancy_ref: Nonempty
    publication_revision: int = Field(ge=1, strict=True)


class Consideration(Revision):
    consideration_ref: Nonempty
    confirmation_basis: Nonempty
