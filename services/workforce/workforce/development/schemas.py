from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, StringConstraints, TypeAdapter, model_validator

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


Keys = Annotated[list[Code], Field(min_length=1, max_length=100)]


class Artifact(Input):
    kind: Literal["text", "url"]
    value: Content
    mutable_source: bool = False

    @model_validator(mode="after")
    def source_type(self):
        if self.kind == "url":
            url = TypeAdapter(HttpUrl).validate_python(self.value)
            if url.username or url.password:
                raise ValueError("Do not embed credentials in a source URL")
        # No copy of a remote source is fetched or claimed by this module.
        self.mutable_source = self.kind == "url"
        return self


class SubmissionCreate(Input):
    activity_key: Code
    criterion_keys: Keys
    statement: Content
    artifact: Artifact

    @model_validator(mode="after")
    def unique_keys(self):
        if len(set(self.criterion_keys)) != len(self.criterion_keys):
            raise ValueError("Criterion keys must be unique")
        return self


class CriterionResult(Input):
    criterion_key: Code
    result: Literal["confirmed", "needs_revision", "not_verified"]
    reason: Content


class ReviewCreate(Input):
    results: Annotated[list[CriterionResult], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_results(self):
        keys = [item.criterion_key for item in self.results]
        if len(set(keys)) != len(keys):
            raise ValueError("One result per criterion required")
        return self


class ReviewView(ResourceView):
    submission_id: UUID
    reviewer_actor_id: UUID
    results: list[CriterionResult]


class SubmissionView(ResourceView):
    plan_id: UUID
    plan_revision: int
    activity_key: str
    attempt_no: int
    criterion_keys: list[str]
    statement: str
    artifact: Artifact
    created_by: UUID


class SubmissionHistory(SubmissionView):
    review: ReviewView | None


class Submissions(BaseModel):
    items: list[SubmissionHistory]


class CriterionProgress(BaseModel):
    key: str
    state: Literal["unsubmitted", "waiting", "confirmed", "needs_revision", "not_verified"]
    submission_id: UUID | None = None
    review_id: UUID | None = None


class Progress(BaseModel):
    criteria: list[CriterionProgress]
    completed_count: int
    total_count: int
