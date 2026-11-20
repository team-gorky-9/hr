"""Командная строка импорта.

    uv run python -m app.ingest --input fixtures/stage_0a --mapping fixtures/stage_0a/mapping.json

В stdout печатается JSON-отчёт (контракт импорта, п. 4), в stderr — одна строка со счётчиками.
Код выхода: 0 — сбоев нет (карантин и конфликты — штатные статусы), 1 — есть статус `error`,
2 — неверные аргументы или пакет не найден.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.ingest.package import load_mapping, read_package
from app.ingest.pipeline import default_batch_label, run_import
from app.ingest.report import ItemStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.ingest", description="Импорт откликов в базу")
    parser.add_argument("--input", required=True, type=Path,
                        help="папка пакета: выгрузка парсера (corpus.jsonl + originals/) или папка с файлами")
    parser.add_argument("--mapping", type=Path, help="mapping.json с явным сопоставлением файлов")
    parser.add_argument("--batch", help="метка запуска (до 64 символов), по умолчанию ingest-<дата-время>")
    parser.add_argument("--report", type=Path, help="сохранить JSON-отчёт ещё и в файл")
    parser.add_argument("--dry-run", action="store_true", help="пробный прогон: всё откатить в конце")
    parser.add_argument("--reredact", action="store_true",
                        help="очистить уже загруженные резюме заново текущими правилами (новая версия текста)")
    return parser


def main(argv: list[str] | None = None, session_factory=None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию не UTF-8

    if not args.input.is_dir():
        print(f"нет папки пакета: {args.input}", file=sys.stderr)
        return 2
    if args.mapping is not None and not args.mapping.is_file():
        print(f"нет файла mapping: {args.mapping}", file=sys.stderr)
        return 2
    batch = args.batch or default_batch_label(datetime.now())
    if len(batch) > 64:
        print("метка --batch длиннее 64 символов", file=sys.stderr)
        return 2

    if session_factory is None:
        from app.db.session import SessionLocal
        session_factory = SessionLocal

    files = read_package(args.input)
    mapping = load_mapping(args.mapping)
    session: Session = session_factory()
    try:
        report = run_import(session, files, mapping, import_batch=batch, commit_each=not args.dry_run,
                            reredact=args.reredact)
        if args.dry_run:
            session.rollback()
    finally:
        session.close()

    payload = report.model_dump_json(indent=2)
    print(payload)
    if args.report is not None:
        args.report.write_text(payload, encoding="utf-8")
    counts = ", ".join(f"{name}={value}" for name, value in report.counts.items() if value)
    history = ", ".join(f"{name}={value}" for name, value in report.history.items())
    reredact = ", ".join(f"{name}={value}" for name, value in report.reredact.items())
    print(f"импорт {batch}: {counts}; история: {history}" + (f"; перечистка: {reredact}" if reredact else ""),
          file=sys.stderr)
    return 1 if report.counts.get(ItemStatus.ERROR.value) else 0


if __name__ == "__main__":
    sys.exit(main())
