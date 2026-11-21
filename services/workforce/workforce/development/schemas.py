from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

from workforce.schemas import Code, Input, Revision, Text

Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class GoalCreate(Input):
    title: Text
    description: Content


class Patch(Revision):
    @model_validator(mode="after")
    def supplied_values(self):
        fields = self.model_fields_set - {"expected_revision"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Supply at least one non-null field")
        return self


class GoalPatch(Patch):
    title: Text | None = None
    description: Content | None = None


class Share(Revision):
    recipient_actor_id: UUID


class Criterion(Input):
    key: Code
    text: Content
    required: Annotated[bool, Field(strict=True)]


class Activity(Input):
    key: Code
    title: Text
    criterion_keys: Annotated[list[Code], Field(min_length=1, max_length=100)]
    resource_note: Content


Criteria = Annotated[list[Criterion], Field(min_length=1, max_length=100)]
Activities = Annotated[list[Activity], Field(min_length=1, max_length=100)]


def validate_plan(criteria, activities):
    keys = [item["key"] for item in criteria]
    activity_keys = [item["key"] for item in activities]
    if len(set(keys)) != len(keys) or len(set(activity_keys)) != len(activity_keys):
        raise ValueError("Criterion and activity keys must be unique")
    for activity in activities:
        refs = activity["criterion_keys"]
        if len(set(refs)) != len(refs) or not set(refs) <= set(keys):
            raise ValueError("Activity must reference unique, existing criteria")


class PlanCreate(Input):
    goal_id: UUID
    goal_revision: Annotated[int, Field(ge=1, strict=True)]
    reviewer_actor_id: UUID
    title: Text
    criteria: Criteria
    activities: Activities

    @model_validator(mode="after")
    def links(self):
        data = self.model_dump()
        validate_plan(data["criteria"], data["activities"])
        return self


class PlanPatch(Patch):
    title: Text | None = None
    criteria: Criteria | None = None
    activities: Activities | None = None
    reviewer_actor_id: UUID | None = None


class Respond(Revision):
    decision: Literal["accept", "return"]
    note: Content


class ResourceView(BaseModel):
    id: UUID
    revision: int
    created_at: datetime
    updated_at: datetime


class GoalView(ResourceView):
    organization_id: UUID
    owner_actor_id: UUID
    title: str
    description: str
    status: Literal["private", "shared"]
    shared_with_actor_id: UUID | None


class PlanView(ResourceView):
    organization_id: UUID
    goal_id: UUID
    owner_actor_id: UUID
    manager_actor_id: UUID
    reviewer_actor_id: UUID
    assignment_basis: dict
    title: str
    criteria: list[Criterion]
    activities: list[Activity]
    goal_revision: int
    goal_snapshot: GoalView
    agreed_revision: int | None
    status: Literal["proposed", "returned", "active", "closed"]
    decision_note: str | None


class Goals(BaseModel):
    items: list[GoalView]


class Plans(BaseModel):
    items: list[PlanView]
