"""Атомарное локальное файловое хранилище документов по требованиям wave-1-common."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import uuid

from .errors import ServiceError


@dataclass(frozen=True)
class StoredFile:
    """Метаданные атомарно сохранённого файла на диске."""

    document_id: uuid.UUID
    storage_key: str
    size_bytes: int
    sha256: str


class LocalFileStorage:
    """Хранение байтов документов внутри FILE_ROOT с записью через временный файл."""

    def __init__(self, root: Path, *, max_bytes: int) -> None:
        self._root = root.resolve()
        self._max_bytes = max_bytes
        self._tmp_dir = self._root / ".tmp"
        self._root.mkdir(parents=True, exist_ok=True)
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _target_relpath(self, organization_id: uuid.UUID, document_id: uuid.UUID) -> Path:
        doc_hex = document_id.hex
        return Path(str(organization_id)) / doc_hex[:2] / doc_hex

    def resolve_key(self, storage_key: str) -> Path:
        """Безопасно разрешить внутренний storage_key без выхода за пределы FILE_ROOT."""
        candidate = (self._root / storage_key).resolve()
        if not candidate.is_relative_to(self._root):
            raise ServiceError(500, "STORAGE_ERROR", "Недопустимый путь к сохранённому файлу.")
        return candidate

    def save_bytes(
        self,
        *,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        data: bytes,
    ) -> StoredFile:
        """Сохранить байты файла во временный файл и атомарно переместить в хранилище."""
        size_bytes = len(data)
        if size_bytes == 0:
            raise ServiceError(422, "VALIDATION_ERROR", "Файл не может быть пустым.", field="file")
        if size_bytes > self._max_bytes:
            raise ServiceError(
                413,
                "FILE_TOO_LARGE",
                f"Размер файла превышает допустимый предел ({self._max_bytes} байт).",
                field="file",
            )

        digest = hashlib.sha256(data).hexdigest()
        rel_path = self._target_relpath(organization_id, document_id)
        final_path = self._root / rel_path
        final_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._tmp_dir / f"{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp_path, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, final_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        return StoredFile(
            document_id=document_id,
            storage_key=rel_path.as_posix(),
            size_bytes=size_bytes,
            sha256=digest,
        )

    def delete_by_key(self, storage_key: str) -> None:
        """Удалить файл по ключу при откате транзакции до commit."""
        path = self.resolve_key(storage_key)
        path.unlink(missing_ok=True)

    def read_bytes(self, storage_key: str) -> bytes:
        """Прочитать сохранённый оригинал документа."""
        path = self.resolve_key(storage_key)
        if not path.is_file():
            raise ServiceError(404, "NOT_FOUND", "Файл документа отсутствует в хранилище.")
        return path.read_bytes()

    def cleanup_orphans(self, active_storage_keys: set[str]) -> int:
        """Удалить временные и сиротские файлы, не связанные с записями документов в БД."""
        removed = 0
        for tmp_file in self._tmp_dir.glob("*.tmp"):
            tmp_file.unlink(missing_ok=True)
            removed += 1
        for path in self._root.rglob("*"):
            if not path.is_file() or path.parent == self._tmp_dir:
                continue
            rel = path.relative_to(self._root).as_posix()
            if rel not in active_storage_keys:
                path.unlink(missing_ok=True)
                removed += 1
        return removed
