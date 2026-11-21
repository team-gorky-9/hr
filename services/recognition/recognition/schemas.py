from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Revision(Input):
    expected_revision: int = Field(ge=1, strict=True)


class WithReason(Revision):
    reason: Text


class ThanksCreate(Input):
    recipient_id: UUID
    text: Text
    requested_visibility: Literal["private", "organization"]


class ThanksEdit(Revision):
    text: Text


class Visibility(Revision):
    choice: Literal["private", "organization", "declined"]


class Moderation(Revision):
    result: Literal["approved", "returned"]
    reason: Text | None = None


class ThanksView(BaseModel):
    id: UUID
    organization_id: UUID
    author_id: UUID
    recipient_id: UUID
    text: str
    revision: int
    status: Literal["pending", "private", "published", "withdrawn"]
    created_at: str
    updated_at: str
    requested_visibility: str | None = None
    recipient_choice: str | None = None
    moderation_status: str | None = None
    moderation_reason: str | None = None
    withdrawal_reason: str | None = None
    history: list[dict] | None = None


class ThanksPage(BaseModel):
    items: list[ThanksView]
    next_cursor: UUID | None
