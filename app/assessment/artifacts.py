"""Versioned computation artifacts. Source access is checked by the caller on every read."""
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


class ProcessingArtifact(Base):
    __tablename__ = "processing_artifacts"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(200), index=True)
    dependencies: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


class ArtifactStore:
    def __init__(self, session: Session, scope: str):
        self.session, self.scope = session, scope

    def key(self, kind: str, dependencies: dict) -> str:
        return fingerprint({"kind": kind, "scope": self.scope, "dependencies": dependencies})

    def get(self, kind: str, dependencies: dict):
        row = self.session.get(ProcessingArtifact, self.key(kind, dependencies))
        return row.payload if row is not None and row.scope == self.scope else None

    def put(self, kind: str, dependencies: dict, payload: dict):
        key = self.key(kind, dependencies)
        existing = self.session.get(ProcessingArtifact, key)
        if existing is not None:
            return existing.payload
        # The surrounding transaction owns publication. Unique key prevents two accepted results.
        self.session.add(ProcessingArtifact(key=key, kind=kind, scope=self.scope,
                                            dependencies=dependencies, payload=payload))
        self.session.flush()
        return payload
