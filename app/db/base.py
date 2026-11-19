"""Общая основа моделей: базовый класс, правила имён ограничений, типовые столбцы."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Единые имена индексов и ограничений: Alembic генерирует одинаковые миграции
# у всех участников, а ошибки из базы понятно читать (например, uq_candidates_code).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Первичный ключ UUID. Значение ставит и Python, и сама база (для вставок через SQL)."""
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def created_at_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Перечисление хранится строкой с CHECK-ограничением, а не нативным ENUM PostgreSQL:
    новое значение добавляется простой миграцией без ALTER TYPE (развилка Р10)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )
