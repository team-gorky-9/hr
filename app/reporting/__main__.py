"""Run with python -m app.reporting."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import store
from .engine import generate
from .analytics import AnalyticsQuery, query_report
from .analysis_excel import analysis_book
from .excel import make_workbook
from .loader import PackageError, load_package


def export(data: bytes, destination: Path):
    if destination.suffix.lower() != ".xlsx":
        raise PackageError("expected_xlsx_destination")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        name = Path(stream.name)
        try:
            stream.write(data)
        except OSError:
            stream.close()
            name.unlink(missing_ok=True)
            raise
    try:
        os.replace(name, destination)
    finally:
        name.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Годовые отчёты о подборе")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate").add_argument("directory", type=Path)
    build = commands.add_parser("generate")
    build.add_argument("directory", type=Path)
    build.add_argument("--year", type=int, required=True)
    commands.add_parser("list").add_argument("--year", type=int)
    write = commands.add_parser("export")
    write.add_argument("snapshot_id")
    write.add_argument("--output", type=Path, required=True)
    analyze = commands.add_parser("query", help="Срез по сохранённому JSON-запросу с необязательной выгрузкой XLSX")
    analyze.add_argument("snapshot_id")
    analyze.add_argument("--query", type=Path, required=True)
    analyze.add_argument("--output", type=Path)
    options = parser.parse_args(argv)
    catalog = store.catalogue_dir()
    try:
        if options.command in {"generate", "validate"}:
            package = load_package(options.directory)
            result = {"applications": len(package.applications), "interviews": len(package.interviews),
                      "duplicates": package.duplicates, "mode": package.manifest.mode}
            if options.command == "generate":
                snapshot = generate(package, options.year)
                result.update(snapshot_id=store.save(snapshot, catalog), totals=snapshot["totals"])
        elif options.command == "list":
            result = store.list_versions(catalog, options.year)
        elif options.command == "query":
            snapshot = store.read(options.snapshot_id, catalog)
            query = AnalyticsQuery.model_validate_json(options.query.read_bytes())
            result = query_report(snapshot, query)
            if options.output:
                export(analysis_book(snapshot, result), options.output)
        else:
            export(make_workbook(store.read(options.snapshot_id, catalog)), options.output)
            result = {"snapshot_id": options.snapshot_id, "exported": True}
    except (ValueError, LookupError, OSError) as exc:
        print(str(exc) if isinstance(exc, ValueError) else "report_io_error", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=not sys.stdout.isatty()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
