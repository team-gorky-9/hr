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
    false,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import (
    Channel,
    CheckStage,
    CompetencyRank,
    FormalRequirementKind,
    RequirementStatus,
    RowOrigin,
    SourceRole,
    VacancyStatus,
    VerificationMethod,
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




# --- Требования к должности ---------------------------------------------------
#
# Единый формат для всех должностей (контракт БД v1.1, п. 4.3): профиль состоит из
# формальных требований (допуск) и компетенций, компетенция — из индикаторов.
# У каждой строки указано, обязательна ли она, где её можно подтвердить и из какого
# документа она взята. Ранг и процент из матрицы заказчика хранятся справочно и
# заполняются только там, где они есть в документе.


class RequirementProfile(Base):
    """Версия требований к должности: формальные требования + компетенции.

    Модель или человек создаёт черновик, кадровик утверждает. Утверждённой может быть
    только одна версия на должность в каждом контуре (рабочем и учебном); оценки
    ссылаются на конкретную версию.
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
    # Контур профиля [v1.5]: false — рабочий, true — учебный (выдуманные правила для проверки системы).
    # Утверждение, нумерация версий и выбор действующего профиля идут отдельно в каждом контуре.
    # Ставится при создании и не меняется: смену отклоняет триггер базы (миграция 0003).
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Кто составил: логин человека или имя модели.
    created_by: Mapped[str] = mapped_column(String(128))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # На каком основании утверждено: «распоряжение № …», «согласовано с начальником отдела».
    approval_basis: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    sources: Mapped[list["ProfileSource"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
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
        # Версии нумеруются в своём контуре: учебный v2 и рабочий v2 одной должности — разные профили.
        UniqueConstraint("position_id", "is_synthetic", "version", name="uq_requirement_profiles_version"),
        Index(
            "uq_requirement_profiles_approved",
            "position_id",
            "is_synthetic",
            unique=True,
            postgresql_where=sa_text("status = 'approved'"),
        ),
    )


class ProfileSource(Base):
    """Документ, из которого собрана версия профиля: ДИ, матрица, текст вакансии.

    Связь с конкретным файлом (по SHA-256 в source_documents) не меняется вместе
    с должностью: старая версия профиля продолжает указывать на свою редакцию ДИ.
    """
    __tablename__ = "requirement_profile_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_profiles.id", ondelete="CASCADE")
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT")
    )
    role: Mapped[SourceRole] = mapped_column(str_enum(SourceRole, "role"))
    # Редакция, которую видно в самом документе: «1.2 от 01.02.2024». У ДИ без номера редакции пусто.
    observed_revision: Mapped[str | None] = mapped_column(String(128))
    # Основной документ профиля (ДИ); вакансия и положения — дополнительные.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    profile: Mapped[RequirementProfile] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("profile_id", "source_document_id", name="uq_requirement_profile_sources_document"),
    )


class _RowSource:
    """Устойчивый ключ строки и её происхождение: ссылки на документы с адресом и
    дословной цитатой — или обоснование, если строку сформулировала команда."""

    # Ключ строки в пакете профиля: «hr.education.level», «py.di.P106». Не меняется между версиями,
    # по нему сверяют таблицу источников, JSON-пакет и контрольные примеры.
    key: Mapped[str] = mapped_column(String(64))
    origin: Mapped[RowOrigin] = mapped_column(str_enum(RowOrigin, "origin"))
    # Список SourceRef (п. 3.6 контракта): документ из источников профиля, адрес, цитата.
    # Строка может опираться на несколько документов (строка матрицы + пункт ДИ).
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Обоснование строки команды или замечание к строке из документа.
    note: Mapped[str | None] = mapped_column(Text)


def _row_source_check() -> CheckConstraint:
    """Строка из документа обязана сослаться хотя бы на один документ; строка команды — иметь обоснование."""
    return CheckConstraint(
        "(origin = 'source' AND jsonb_array_length(source_refs) > 0)"
        " OR (origin = 'team' AND note IS NOT NULL)",
        name="row_source",
    )


def _check_stage_check() -> CheckConstraint:
    """На первичном отборе проверяется только то, что видно по резюме или подтверждается
    документом (предварительно — по резюме). Интервью и тест — не этап screening."""
    return CheckConstraint(
        "check_stage = 'interview' OR verification IN ('resume', 'documents')",
        name="check_stage_verification",
    )


class FormalRequirement(_RowSource, Base):
    """Условие допуска (образование, направление, стаж): выполнено или нет.
    Проверяется отдельно от компетенций и не «добирается» баллами."""
    __tablename__ = "formal_requirements"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_profiles.id", ondelete="CASCADE")
    )
    kind: Mapped[FormalRequirementKind] = mapped_column(str_enum(FormalRequirementKind, "kind"))
    description: Mapped[str] = mapped_column(Text)
    # Машиночитаемое правило в формате params 0.1 (app/schemas/requirements.py, контракт п. 3.5), например
    # {"schema_version": "0.1", "alternatives": [{"key": "hr.education.level.alt1", "level": "высшее"}]}.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Обязательно по источнику (false — «будет преимуществом»). Входит в итог formal_result.
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    verification: Mapped[VerificationMethod] = mapped_column(str_enum(VerificationMethod, "verification"))
    # На каком этапе проверяется [v1.5]; в итог formal_result входят только строки этапа screening.
    check_stage: Mapped[CheckStage] = mapped_column(
        str_enum(CheckStage, "check_stage"), default=CheckStage.SCREENING, server_default="screening"
    )
    # Что считать выполнением, невыполнением и нехваткой сведений: {"met": …, "not_met": …, "unknown": …, "limit": …}.
    acceptance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    profile: Mapped[RequirementProfile] = relationship(back_populates="formal_requirements")

    __table_args__ = (
        UniqueConstraint("profile_id", "key", name="uq_formal_requirements_profile_key"),
        _row_source_check(),
        _check_stage_check(),
    )


class Competency(_RowSource, Base):
    """Компетенция — группа индикаторов на одну тему.

    Ранг и эталонный уровень заполняются только из матрицы заказчика (сейчас она есть
    у одной должности) и хранятся справочно; для других должностей они пусты.
    """
    __tablename__ = "competencies"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_profiles.id", ondelete="CASCADE")
    )
    rank: Mapped[CompetencyRank | None] = mapped_column(str_enum(CompetencyRank, "rank"))
    code: Mapped[str] = mapped_column(String(32))  # «ПАК», «ИТК», «PY-DB»
    name: Mapped[str] = mapped_column(String(512))
    # Эталонный уровень из матрицы: «90–100 процентов» → 90 и 100. Оба пусты, если в источнике нет.
    target_level_min: Mapped[int | None] = mapped_column(SmallInteger)
    target_level_max: Mapped[int | None] = mapped_column(SmallInteger)
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
        UniqueConstraint("profile_id", "key", name="uq_competencies_profile_key"),
        CheckConstraint(
            "(target_level_min IS NULL AND target_level_max IS NULL)"
            " OR (target_level_min >= 0 AND target_level_min <= target_level_max AND target_level_max <= 100)",
            name="target_level_range",
        ),
        _row_source_check(),
    )


class CompetencyIndicator(_RowSource, Base):
    """Конкретное проверяемое требование: «умеет работать с базами данных…»."""
    __tablename__ = "competency_indicators"

    id: Mapped[uuid.UUID] = uuid_pk()
    competency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    # Обязательно или желательно («будет преимуществом» в вакансии).
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    verification: Mapped[VerificationMethod] = mapped_column(str_enum(VerificationMethod, "verification"))
    check_stage: Mapped[CheckStage] = mapped_column(
        str_enum(CheckStage, "check_stage"), default=CheckStage.SCREENING, server_default="screening"
    )
    acceptance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Строка сохранена ради прослеживаемости, но в оценку не входит (например, право, а не компетенция).
    excluded_from_scoring: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    competency: Mapped[Competency] = relationship(back_populates="indicators")

    __table_args__ = (
        UniqueConstraint("competency_id", "key", name="uq_competency_indicators_competency_key"),
        _row_source_check(),
        _check_stage_check(),
    )
