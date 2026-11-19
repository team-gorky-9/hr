"""Должности, вакансии и требования к кандидату (развилка Р11)."""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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
from app.db.enums import (
    Channel,
    CompetencyRank,
    FormalRequirementKind,
    RequirementStatus,
    VacancyStatus,
)


class Position(Base):
    """Должность из штатного расписания и её должностная инструкция."""
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True)  # «python-dev», «hr-consultant»
    title: Mapped[str] = mapped_column(String(512))
    employer: Mapped[str] = mapped_column(String(512))
    # Должность муниципальной службы: действуют ограничения 25-ФЗ и квалификационные требования.
    is_municipal_service: Mapped[bool] = mapped_column(Boolean)
    service_group: Mapped[str | None] = mapped_column(String(256))
    job_description_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at_column()


class Vacancy(Base):
    """Публикация должности на площадке. У одной должности может быть несколько публикаций."""
    __tablename__ = "vacancies"

    id: Mapped[uuid.UUID] = uuid_pk()
    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"))
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    title: Mapped[str] = mapped_column(String(512))
    posting_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    status: Mapped[VacancyStatus] = mapped_column(
        str_enum(VacancyStatus, "status"), default=VacancyStatus.OPEN, server_default="open"
    )
    opened_at: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at_column()

    position: Mapped[Position] = relationship()


class RequirementProfile(Base):
    """Версия требований к должности: формальные требования + матрица компетенций.

    Модель или человек создаёт черновик, кадровик утверждает. Утверждённой
    может быть только одна версия на должность; оценки ссылаются на конкретную версию.
    """
    __tablename__ = "requirement_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[RequirementStatus] = mapped_column(
        str_enum(RequirementStatus, "status"),
        default=RequirementStatus.DRAFT,
        server_default="draft",
    )
    # Кто составил: логин человека или имя модели.
    created_by: Mapped[str] = mapped_column(String(128))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    formal_requirements: Mapped[list["FormalRequirement"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FormalRequirement.sort_order",
    )
    competencies: Mapped[list["Competency"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Competency.sort_order",
    )

    __table_args__ = (
        UniqueConstraint("position_id", "version", name="uq_requirement_profiles_version"),
        Index(
            "uq_requirement_profiles_approved",
            "position_id",
            unique=True,
            postgresql_where=sa_text("status = 'approved'"),
        ),
    )


class FormalRequirement(Base):
    """Юридически значимое требование (образование, направление, стаж).
    Проверяется отдельно от компетенций и не «добирается» баллами."""
    __tablename__ = "formal_requirements"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_profiles.id", ondelete="CASCADE")
    )
    kind: Mapped[FormalRequirementKind] = mapped_column(str_enum(FormalRequirementKind, "kind"))
    description: Mapped[str] = mapped_column(Text)
    # Машиночитаемые условия, например
    # {"min_level": "высшее", "fields": ["Юриспруденция", "ГМУ"], "retraining_allowed": true}.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Дословная цитата из должностной инструкции.
    source_quote: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    profile: Mapped[RequirementProfile] = relationship(back_populates="formal_requirements")


class Competency(Base):
    """Компетенция из матрицы по образцу заказчика: ранг, код, эталонный уровень."""
    __tablename__ = "competencies"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_profiles.id", ondelete="CASCADE")
    )
    rank: Mapped[CompetencyRank] = mapped_column(str_enum(CompetencyRank, "rank"))
    code: Mapped[str] = mapped_column(String(32))  # «ПАК», «ИТК», «РК», «ОИК», «ДК»
    name: Mapped[str] = mapped_column(String(512))
    # Эталонный уровень развития в процентах: «90–100 процентов» → 90 и 100.
    target_level_min: Mapped[int] = mapped_column(SmallInteger)
    target_level_max: Mapped[int] = mapped_column(SmallInteger)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    profile: Mapped[RequirementProfile] = relationship(back_populates="competencies")
    indicators: Mapped[list["CompetencyIndicator"]] = relationship(
        back_populates="competency",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CompetencyIndicator.sort_order",
    )

    __table_args__ = (
        UniqueConstraint("profile_id", "code", name="uq_competencies_profile_code"),
        CheckConstraint(
            "target_level_min >= 0 AND target_level_min <= target_level_max AND target_level_max <= 100",
            name="target_level_range",
        ),
    )


class CompetencyIndicator(Base):
    """Поведенческий индикатор компетенции: «умеет работать с базами данных…»."""
    __tablename__ = "competency_indicators"

    id: Mapped[uuid.UUID] = uuid_pk()
    competency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    competency: Mapped[Competency] = relationship(back_populates="indicators")
