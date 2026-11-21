from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Revision(Input):
    expected_revision: int = Field(ge=1)

class CreateCase(Input):
    rule_version_id: UUID
    statement: Text

class EditCase(Revision):
    statement: Text

class Assignment(Revision):
    specialist_actor_id: UUID
    secretary_actor_id: UUID
    assignment_basis: Text

class StaffConfirmation(Revision):
    state: Literal["confirmed", "unknown"]
    source_reference: Text

class ChecklistItem(Input):
    key: Text
    result: Literal["present", "missing", "unreadable", "needs_clarification"]
    document_id: UUID | None = None
    reason: str = Field(default="", max_length=10000)

class Completeness(Revision):
    items: list[ChecklistItem] = Field(min_length=1, max_length=100)
    public_message: Text

class Addendum(Revision):
    text: Text
    document_ids: list[UUID] = Field(default_factory=list, max_length=100)
