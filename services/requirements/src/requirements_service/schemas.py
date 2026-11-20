"""Pydantic DTO запросов и ответов HTTP API сервиса требований."""
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class _StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PositionCreateIn(_StrictIn):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    title: str = Field(min_length=1, max_length=256)


class PositionOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    title: str
    revision: int
    created_at: datetime
    updated_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: str
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str
    revision: int
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SourceOut(DocumentOut):
    position_code: str
    extraction_status: Literal["ready", "unavailable", "failed"]
    extracted_text: str | None = None
    text_origin: Literal["extracted", "manual_transcription"] | None = None
    transcription_basis: str | None = None
    reason: str | None = None


class SourceTranscriptionIn(_StrictIn):
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1)
    transcription_basis: str = Field(min_length=1, max_length=512)


class DraftCreateIn(_StrictIn):
    position_code: str = Field(min_length=1, max_length=64)
    content: dict[str, Any]


class DraftPatchIn(_StrictIn):
    expected_revision: int = Field(ge=1)
    content: dict[str, Any]
    change_reason: str = Field(min_length=1, max_length=512)


class DraftSubmitIn(_StrictIn):
    expected_revision: int = Field(ge=1)
    reviewer_actor_id: uuid.UUID


class DraftReviewIn(_StrictIn):
    expected_revision: int = Field(ge=1)
    result: Literal["accepted", "returned"]
    note: str | None = Field(default=None, max_length=2000)
    override_reason: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _check_returned_note(self):
        if self.result == "returned" and (not self.note or not self.note.strip()):
            raise ValueError("при возврате черновика необходимо указать замечание в note")
        return self


class DraftApproveIn(_StrictIn):
    expected_revision: int = Field(ge=1)
    approval_basis: str = Field(min_length=1, max_length=1000)


class ProfileReviseIn(_StrictIn):
    change_reason: str = Field(min_length=1, max_length=512)


class DraftOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    position_code: str
    contour: Literal["training", "working"]
    status: Literal["editing", "in_review", "returned", "approved"]
    revision: int
    content_revision: int
    content: dict[str, Any]
    review_note: str | None = None
    assigned_reviewer_actor_id: uuid.UUID | None = None
    accepted_content_revision: int | None = None
    accepted_source_revisions: dict[str, int] | None = None
    accepted_by_actor_id: uuid.UUID | None = None
    accepted_at: datetime | None = None
    created_by_actor_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DraftEventOut(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    organization_id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    draft_revision: int
    content_revision: int
    reason: str | None = None
    details: dict[str, Any]
    created_at: datetime


class SourceSnapshotOut(BaseModel):
    source_document_id: uuid.UUID
    source_revision: int
    kind: str
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str
    text_origin: str | None = None
    transcription_basis: str | None = None
    extracted_text: str | None = None


class ApprovedProfileOut(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    organization_id: uuid.UUID
    position_code: str
    version: int
    contour: Literal["training", "working"]
    revision: int
    content: dict[str, Any]
    sources_snapshot: list[SourceSnapshotOut]
    approval_basis: str
    approved_by_actor_id: uuid.UUID
    approved_at: datetime
    is_current: bool
    created_at: datetime
    updated_at: datetime


class DeliveryOut(BaseModel):
    event_id: uuid.UUID
    event_type: str
    status: Literal["pending", "sent", "failed"]
    attempts: int
    last_error: str | None = None
    next_attempt_at: datetime
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PageOut(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class HealthOut(BaseModel):
    implementation_stage: int = 1
    integration_mode: str = "standalone"
    status: str
    service: str
    auth_mode: str


class ReadyOut(BaseModel):
    status: str
    db: str
    migrations: str
    broker: str
    auth_mode: str
