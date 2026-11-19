"""Кандидат: одно резюме и всё, что из него извлечено.

Три слоя данных о кандидате:
1. source_documents — исходный файл, не меняется;
2. candidate_texts — текст без персональных данных, его видит модель и на него ссылаются цитаты;
3. candidate_cards — карточка, извлечённая из текста; хранятся все версии.
Персональные данные лежат отдельно в candidate_pii (слепой режим).
"""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, uuid_pk
from app.db.models.sources import SourceDocument


class Candidate(Base):
    """Одно резюме — одна запись (развилка Р2). Склейка дублей одного человека — позже."""
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Читаемый код для людей и логов, например «py-0005» (развилка Р6).
    code: Mapped[str] = mapped_column(String(32), unique=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="RESTRICT"), unique=True
    )
    # Заголовок резюме: «Python Backend Developer (FastAPI, PostgreSQL)».
    headline: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_document: Mapped[SourceDocument] = relationship()
    pii: Mapped["CandidatePii | None"] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )


class CandidatePii(Base):
    """Персональные данные. Читаются только через repository.get_candidate_pii,
    который пишет запись в журнал аудита. В модель не передаются."""
    __tablename__ = "candidate_pii"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str | None] = mapped_column(String(512))
    gender: Mapped[str | None] = mapped_column(String(16))
    birth_date: Mapped[date | None] = mapped_column(Date)
    age: Mapped[int | None] = mapped_column(SmallInteger)
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(256))
    city: Mapped[str | None] = mapped_column(String(256))
    citizenship: Mapped[str | None] = mapped_column(String(256))
    # Ссылки на GitHub, соцсети и т.п.: по ним можно узнать человека.
    links: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Прочее, что импорт счёл персональным (желаемая зарплата и т.п.).
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    candidate: Mapped[Candidate] = relationship(back_populates="pii")


class CandidateText(Base):
    """Текст резюме без персональных данных. Версия меняется, если улучшили очистку."""
    __tablename__ = "candidate_texts"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean)
    # Чем очищали: имя и версия функции импорта, чтобы понимать происхождение текста.
    redaction_method: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_candidate_texts_version"),
        # Ровно одна текущая версия на кандидата.
        Index(
            "uq_candidate_texts_current",
            "candidate_id",
            unique=True,
            postgresql_where=sa_text("is_current"),
        ),
    )


class CandidateCard(Base):
    """Карточка кандидата (развилка Р1: гибрид).

    card — документ по схеме app.schemas.card.CandidateCard, проверяется Pydantic
    при записи. Отдельные столбцы дублируют поля карточки, по которым нужен
    быстрый фильтр. Навыки разложены в candidate_skills.
    Все версии хранятся (развилка Р3): видно, какая модель и промпт дали результат.
    """
    __tablename__ = "candidate_cards"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    # Из какого очищенного текста извлечена карточка.
    candidate_text_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_texts.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean)
    # Кто извлёк: «yandexgpt-lite/latest», «parser-hh-txt v1», «manual».
    extractor: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    card: Mapped[dict[str, Any]] = mapped_column(JSONB)
    experience_years: Mapped[float | None] = mapped_column(Numeric(4, 1, asdecimal=False))
    education_level: Mapped[str | None] = mapped_column(String(64))
    missing_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    created_at: Mapped[datetime] = created_at_column()

    skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="card", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_candidate_cards_version"),
        Index(
            "uq_candidate_cards_current",
            "candidate_id",
            unique=True,
            postgresql_where=sa_text("is_current"),
        ),
    )


class CandidateSkill(Base):
    """Навык из карточки отдельной строкой — для запросов «все, у кого есть FastAPI»."""
    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = uuid_pk()
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_cards.id", ondelete="CASCADE"))
    # Повторяет candidate_id карточки, чтобы поиск по навыку не требовал лишнего соединения.
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(256))  # как написано в резюме
    normalized: Mapped[str] = mapped_column(String(256), index=True)  # для поиска
    level: Mapped[str | None] = mapped_column(String(64))

    card: Mapped[CandidateCard] = relationship(back_populates="skills")

    __table_args__ = (UniqueConstraint("card_id", "normalized", name="uq_candidate_skills_card_skill"),)
