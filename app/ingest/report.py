"""Отчёт прогона импорта (контракт импорта, п. 4).

В отчёт нельзя класть текст резюме и значения ПДн: только путь в пакете, SHA-256,
статус, идентификаторы записей и короткую причину.
"""
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ItemStatus(StrEnum):
    IMPORTED = "imported"                        # новый кандидат, текст и отклик
    APPLICATION_ADDED = "application_added"      # тот же файл на другую вакансию: второй отклик
    DUPLICATE_SKIPPED = "duplicate_skipped"      # тот же файл на ту же вакансию: ничего не создано
    EXCLUDED_NON_RESUME = "excluded_non_resume"  # служебный документ: сохранён без кандидата
    CONFLICT = "conflict"                        # код кандидата занят другим файлом: на ручную сверку
    QUARANTINED = "quarantined"                  # проблема в данных: на ручную сверку, к модели не идёт
    ERROR = "error"                              # сбой программы или базы


class ReportItem(BaseModel):
    source_path: str
    sha256: str | None = None
    status: ItemStatus
    document_kind: str | None = None
    candidate_code: str | None = None
    candidate_id: uuid.UUID | None = None
    candidate_text_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    # Учебный кандидат (mapping: synthetic = true) — в учебном контуре, не в рабочих списках.
    is_synthetic: bool | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    # «История общения» и подвал резюме (ingest-02). Только счётчики: названия и даты — в базе.
    posting_found: bool | None = None   # у основного отклика найдена публикация hh
    history_added: int = 0              # внешних откликов создано в этом прогоне
    history_existing: int = 0           # внешних откликов уже было (повтор)
    # --reredact: updated — новая версия текста, unchanged — правила дали тот же текст, failed — не прошёл проверку.
    reredact: str | None = None


class ImportReport(BaseModel):
    import_batch: str
    started_at: datetime
    finished_at: datetime | None = None
    dry_run: bool = False
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: dict[str, int] = Field(default_factory=dict)
    history: dict[str, int] = Field(default_factory=dict)
    reredact: dict[str, int] = Field(default_factory=dict)
    items: list[ReportItem] = Field(default_factory=list)

    def add(self, item: ReportItem) -> None:
        self.items.append(item)

    def finish(self, finished_at: datetime) -> None:
        self.finished_at = finished_at
        self.counts = {"total": len(self.items)} | {status.value: 0 for status in ItemStatus}
        self.warnings = {}
        self.history = {
            "responses_with_posting": sum(bool(item.posting_found) for item in self.items),
            "applications_added": sum(item.history_added for item in self.items),
            "applications_existing": sum(item.history_existing for item in self.items),
        }
        self.reredact = {}
        for item in self.items:
            if item.reredact:
                self.reredact[item.reredact] = self.reredact.get(item.reredact, 0) + 1
            self.counts[item.status.value] += 1
            for warning in item.warnings:
                self.warnings[warning] = self.warnings.get(warning, 0) + 1
