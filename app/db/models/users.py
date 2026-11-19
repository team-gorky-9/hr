"""Пользователи платформы и журнал действий (152-ФЗ, объяснимость)."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Index, String, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import AuditAction, UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    login: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "role"))
    # Для сотрудников департаментов: какое подразделение представляет.
    department: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    created_at: Mapped[datetime] = created_at_column()


class AuditLog(Base):
    """Кто, когда и зачем открыл персональные данные или вызвал модель.

    Записи только добавляются. entity_id хранится строкой: журнал ссылается
    на записи разных таблиц и не должен мешать их удалению.
    """
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Порядок записей журнала (created_at одинаков внутри одной транзакции).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[AuditAction] = mapped_column(str_enum(AuditAction, "action"))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)
