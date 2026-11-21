"""Сохранённая подборка HR по вакансии (wave-3-matching-stage-1, раздел 3C, миграция 0011).

Подборка — датированный факт расчёта поиска по конкретной редакции вакансии. Она не отклик,
не приглашение, не запись резерва и не право на контакт. Повторный расчёт — новая строка.
items хранит только разрешённую выдачу и ссылки на версии источников (candidate_text_id и границы
фрагмента), но не сам текст: при чтении фрагмент берётся из действующего источника, а
отозванный или заменённый текст из старого снимка не раскрывается."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class MatchingSuggestion(Base):
    __tablename__ = "matching_suggestions"

    id: Mapped[uuid.UUID] = uuid_pk()
    vacancy_system: Mapped[str] = mapped_column(String(16))
    vacancy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    vacancy_revision: Mapped[int] = mapped_column(Integer)
    # Снимок вакансии без текста объявления: ref, title, position_code, status, observed_at, profile_ref.
    vacancy: Mapped[dict[str, Any]] = mapped_column(JSONB)
    contour: Mapped[str] = mapped_column(String(16))
    source_mode: Mapped[str] = mapped_column(String(16))
    search_query: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_limit: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    semantic_status: Mapped[str] = mapped_column(String(16))
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Время расчёта ставит приложение (а не now() транзакции), чтобы версии одной транзакции различались.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_matching_suggestions_vacancy", "vacancy_system", "vacancy_id", "created_at"),)
