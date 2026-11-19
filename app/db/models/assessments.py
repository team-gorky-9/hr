"""Оценка кандидата по требованиям должности (развилка Р12).

Оценка привязана к паре «кандидат × версия требований», а не к отклику:
кандидата оцениваем по всем должностям, в том числе тем, куда он не откликался.
Решение по кандидату принимает человек — оно хранится в stage_events, не здесь.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import CheckResult


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_profiles.id", ondelete="CASCADE")
    )
    # По какой версии карточки оценивали.
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_cards.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean)
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    # Итог по формальным требованиям: не выполнено хотя бы одно обязательное → not_met.
    formal_result: Mapped[CheckResult] = mapped_column(str_enum(CheckResult, "formal_result"))
    # Итоговый балл 0–100 по компетенциям; пусто, если оценить нельзя.
    overall_score: Mapped[int | None] = mapped_column(SmallInteger)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    formal_checks: Mapped[list["FormalCheck"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True
    )
    competency_scores: Mapped[list["CompetencyScore"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "profile_id", "version", name="uq_assessments_version"
        ),
        Index(
            "uq_assessments_current",
            "candidate_id",
            "profile_id",
            unique=True,
            postgresql_where=sa_text("is_current"),
        ),
        CheckConstraint(
            "overall_score IS NULL OR overall_score BETWEEN 0 AND 100", name="overall_score_range"
        ),
    )


class FormalCheck(Base):
    """Результат проверки одного формального требования с доказательствами."""
    __tablename__ = "formal_checks"

    id: Mapped[uuid.UUID] = uuid_pk()
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE")
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("formal_requirements.id", ondelete="CASCADE")
    )
    result: Mapped[CheckResult] = mapped_column(str_enum(CheckResult, "result"))
    explanation: Mapped[str | None] = mapped_column(Text)
    # Список app.schemas.card.Evidence: цитата + позиция в очищенном тексте (развилка Р4).
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")

    assessment: Mapped[Assessment] = relationship(back_populates="formal_checks")


class CompetencyScore(Base):
    """Уровень одной компетенции у кандидата с доказательствами."""
    __tablename__ = "competency_scores"

    id: Mapped[uuid.UUID] = uuid_pk()
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE")
    )
    competency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE")
    )
    # 0–100, как эталон в матрице; пусто — в резюме нет сведений, нужно уточнить на интервью.
    level: Mapped[int | None] = mapped_column(SmallInteger)
    explanation: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")

    assessment: Mapped[Assessment] = relationship(back_populates="competency_scores")

    __table_args__ = (
        CheckConstraint("level IS NULL OR level BETWEEN 0 AND 100", name="level_range"),
    )
