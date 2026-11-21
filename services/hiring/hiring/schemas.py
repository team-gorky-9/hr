"""Request bodies. Fields outside the specification give 422 (extra="forbid")."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Key = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[a-z0-9_.-]+$")]
Revision = Annotated[int, Field(ge=1)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicationRef(Strict):
    system: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    id: UUID


class CandidateRef(Strict):
    system: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    id: UUID
    display_name: Text


class PositiveSelection(Strict):
    application_ref: ApplicationRef
    candidate_ref: CandidateRef
    organization_id: UUID
    department_id: UUID
    position_code: Key
    outcome: str
    decided_at: datetime
    decided_by_actor_id: UUID
    decision_basis: Text
    is_synthetic: bool


class ChecklistEntry(Strict):
    key: Key
    title: Text
    required: bool


class CreateCase(Strict):
    selection: PositiveSelection
    candidate_actor_id: UUID | None = None
    identity_basis: Text | None = None
    checklist: Annotated[list[ChecklistEntry], Field(min_length=1, max_length=50)]
    checklist_version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

    @model_validator(mode="after")
    def check(self):
        keys = [item.key for item in self.checklist]
        if len(keys) != len(set(keys)):
            raise ValueError("checklist keys must be unique")
        if self.candidate_actor_id is not None and self.identity_basis is None:
            raise ValueError("identity_basis is required when candidate_actor_id is given")
        return self


class RequestDocuments(Strict):
    expected_revision: Revision
    message: Text


class SubmitItem(Strict):
    expected_revision: Revision  # revision of the checklist item, not of the case
    document_id: UUID
    comment: Text | None = None


class ReviewItem(Strict):
    expected_revision: Revision  # revision of the checklist item
    result: Literal["accepted", "needs_revision"]
    reason: Text | None = None

    @model_validator(mode="after")
    def reason_for_return(self):
        if self.result == "needs_revision" and self.reason is None:
            raise ValueError("reason is required to return a document")
        return self


class Ready(Strict):
    expected_revision: Revision


class Basis(Strict):
    document_id: UUID
    reference: Text
    issued_on: date


class Start(Strict):
    expected_revision: Revision
    starts_on: date
    basis: Basis
    confirmation_basis: Text


class Withdraw(Strict):
    expected_revision: Revision
    reason: Text


class LinkAccount(Strict):
    expected_revision: Revision
    candidate_actor_id: UUID
    identity_basis: Text


class CorrectStart(Strict):
    expected_revision: Revision
    starts_on: date | None = None
    basis: Basis | None = None
    reason: Text

    @model_validator(mode="after")
    def something_changes(self):
        if self.starts_on is None and self.basis is None:
            raise ValueError("starts_on or basis is required")
        return self


class ExternalRef(Strict):
    system: Literal["workforce", "external"]
    id: UUID


class RecordAssignment(Strict):
    expected_revision: Revision
    employee_ref: ExternalRef
    assignment_ref: ExternalRef
    actual_starts_on: date
    confirmation_basis: Text

    @field_validator("assignment_ref")
    @classmethod
    def same_space(cls, value, info):
        employee = info.data.get("employee_ref")
        if employee is not None and employee.system != value.system:
            raise ValueError("employee_ref and assignment_ref must come from the same system")
        return value


DOCUMENT_KINDS = ("hiring_application", "hiring_evidence", "employment_basis")  # дела оформления


# --- candidate-portal (wave-5-candidate-portal-stage-1, 5A) ---------------------------------

class PortalVacancyRef(Strict):
    system: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    id: UUID
    revision: Revision


class CandidateContact(Strict):
    """Контакт, который сообщил сам кандидат; внешне не проверен."""
    channel: Literal["email", "phone", "messenger", "other"]
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


class CreateCandidateRequest(Strict):
    vacancy_ref: PortalVacancyRef | None = None
    message: Text
    contact: CandidateContact


class UpdateCandidateRequest(Strict):
    expected_revision: Revision
    message: Text | None = None
    contact: CandidateContact | None = None
    vacancy_ref: PortalVacancyRef | None = None
    clear_vacancy: bool = False  # явный отказ от выбранной вакансии (null в vacancy_ref неотличим от «не менять»)

    @model_validator(mode="after")
    def something_changes(self):
        if self.clear_vacancy and self.vacancy_ref is not None:
            raise ValueError("clear_vacancy and vacancy_ref cannot be combined")
        if not (self.message or self.contact or self.vacancy_ref or self.clear_vacancy):
            raise ValueError("nothing to change")
        return self


class SubmitCandidateRequest(Strict):
    expected_revision: Revision


REQUEST_DOCUMENT_KINDS = ("candidate_resume", "candidate_addendum")
REQUEST_STATUSES = ("draft", "submitted", "needs_information", "ready", "forwarded", "closed", "withdrawn")
