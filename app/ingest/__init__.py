"""Импорт откликов: чтение пакета, очистка ПДн, запись в базу, отчёт.

Контракт: docs/contracts/import.md. Устройство: docs/modules/ingest.md.
Запуск: `uv run python -m app.ingest --input <папка> [--mapping mapping.json]`.
"""
from app.ingest.package import InputFile, load_mapping, read_package
from app.ingest.pipeline import run_import
from app.ingest.redact import REDACTION_METHOD, Redacted, RedactionError, redact
from app.ingest.report import ImportReport, ItemStatus, ReportItem

__all__ = [
    "REDACTION_METHOD",
    "ImportReport",
    "InputFile",
    "ItemStatus",
    "Redacted",
    "RedactionError",
    "ReportItem",
    "load_mapping",
    "read_package",
    "redact",
    "run_import",
]
