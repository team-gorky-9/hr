"""Исходные документы ровно в том виде, в каком они пришли."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, str_enum, uuid_pk
from app.db.enums import Channel, DocumentKind, FileFormat


class SourceDocument(Base):
    """Резюме, должностная инструкция, текст вакансии, положение.

    Запись не меняется после импорта: всё, что получено из документа
    (очищенный текст, карточка, оценки), хранится в других таблицах со ссылкой сюда.
    raw_text может содержать персональные данные, поэтому в модель уходит
    только очищенный текст из candidate_texts.
    """
    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[DocumentKind] = mapped_column(str_enum(DocumentKind, "kind"))
    channel: Mapped[Channel] = mapped_column(str_enum(Channel, "channel"))
    file_format: Mapped[FileFormat] = mapped_column(str_enum(FileFormat, "file_format"))
    # Путь в исходном архиве, например «Python-разработчик/отклик 5.txt» (в NFC).
    original_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(512))
    # SHA-256 содержимого файла: повторный импорт того же файла не создаёт дубль.
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    raw_text: Mapped[str] = mapped_column(Text)
    # Метка запуска импорта, чтобы найти и при необходимости откатить одну загрузку.
    import_batch: Mapped[str | None] = mapped_column(String(64), index=True)
    imported_at: Mapped[datetime] = created_at_column()
