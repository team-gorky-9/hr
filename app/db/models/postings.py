"""Import evidence belongs to an application, not the deduplicated candidate."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, uuid_pk


class ApplicationPostingSource(Base):
    """An immutable observation of an application's source in a package snapshot."""

    __tablename__ = "application_posting_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(Text)
    dataset_sha256: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    source_path: Mapped[str] = mapped_column(Text)
    source_folder: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint(
            "application_id", "dataset_id", "dataset_sha256", "channel", "source_path", "source_sha256",
            name="uq_application_posting_sources_origin",
        ),
        CheckConstraint("btrim(dataset_id) <> ''", name="dataset_id_nonempty"),
        CheckConstraint("dataset_sha256 ~ '^[0-9a-f]{64}$'", name="dataset_sha256_format"),
        CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="source_sha256_format"),
    )
