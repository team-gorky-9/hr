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
