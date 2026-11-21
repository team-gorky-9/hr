"""Immutable acknowledgement of exact feedback versions, owned by legacy HR."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, uuid_pk


class FeedbackReview(Base):
    __tablename__ = "feedback_reviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at_column()
    basis: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    request_payload: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[str] = mapped_column(String(32))
    checked_seq: Mapped[int] = mapped_column(Integer)
    stage_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stage_events.id", ondelete="RESTRICT"))


class FeedbackReviewItem(Base):
    __tablename__ = "feedback_review_items"

    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feedback_reviews.id", ondelete="CASCADE"), primary_key=True)
    feedback_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("department_feedback.id", ondelete="RESTRICT"), primary_key=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handoff_attempts.id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column(Integer)
