"""Векторы фрагментов резюме для поиска по смыслу (развилка Р7)."""
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import ChunkKind


class Embedding(Base):
    """Вектор одного фрагмента очищенного текста резюме.

    Размерность не зафиксирована (развилка Р9): она зависит от модели эмбеддингов,
    а модель выбирает модуль поиска. Векторы разных моделей несравнимы, поэтому
    поиск всегда фильтрует по столбцу model. Индекс для приближённого поиска
    (HNSW) требует фиксированной размерности и добавляется миграцией, когда модель выбрана.
    """
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    candidate_text_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_texts.id", ondelete="CASCADE")
    )
    chunk_kind: Mapped[ChunkKind] = mapped_column(str_enum(ChunkKind, "chunk_kind"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    # Фрагмент и его границы в очищенном тексте: поиск сразу показывает, что совпало.
    text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[list[float]] = mapped_column(Vector())
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint(
            "candidate_text_id", "chunk_kind", "chunk_index", "model", name="uq_embeddings_chunk"
        ),
    )
