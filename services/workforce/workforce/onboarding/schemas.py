from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from workforce.schemas import Code, Input, Revision, Text


class Assign(Input):
    workforce_assignment_id: UUID
    template_code: Code
    template_version: Annotated[int, Field(ge=1, strict=True)]


class Cancel(Revision):
    reason: Text


class TemplateStep(BaseModel):
    key: str
    title: str
    description: str
    material_url: str | None
    kind: Literal["acknowledgement"]


class TemplateView(BaseModel):
    code: str
    version: int
    title: str
    steps: list[TemplateStep]


class ProgramStep(BaseModel):
    key: str
    title: str
    description: str
    material_url: str | None
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None


class ProgramView(BaseModel):
    id: UUID
    organization_id: UUID
    employee_id: UUID
    workforce_assignment_id: UUID
    template_code: str
    template_version: int
    assigned_by_actor_id: UUID
    assigned_at: datetime
    revision: int
    status: Literal["active", "intro_completed", "cancelled"]
    steps: list[ProgramStep]
    completed_count: int
    total_count: int
    cancel_reason: str | None
    assignment_state: Literal["active", "inactive"]
    account_link_required: bool


class Templates(BaseModel):
    items: list[TemplateView]


class Programs(BaseModel):
    items: list[ProgramView]
