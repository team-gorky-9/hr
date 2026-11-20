"""Verify the reporting path on the supplied case archive, printing aggregate counts only."""
import argparse
from collections import Counter
import csv
from datetime import date, timedelta
import json
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import ZipFile

from app.ingest.extract import docx_text
from app.ingest.history import parse_history
from app.ingest.package import RESUME_NAME, folder_key
from app.reporting.engine import generate
from app.reporting.excel import make_workbook
from app.reporting.__main__ import export
from app.reporting import store
from app.reporting.loader import load_package


def check(archive, output=None, save_snapshots=False):
    mapping = json.loads((Path(__file__).resolve().parents[1] / "fixtures/kadry_mapping.json").read_bytes())
    folders = {folder_key(k) for k, v in mapping["folders"].items() if v == "hr-consultant"}
    observed = Counter()
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        with ZipFile(archive, metadata_encoding="utf-8") as source, (directory / "applications.csv").open(
            "w", encoding="utf-8", newline=""
        ) as out:
            writer = csv.writer(out)
            writer.writerow(["application_key", "vacancy_key", "applied_on"])
            for name in source.namelist():
                path = PurePosixPath(name)
                if "__MACOSX" in path.parts or folder_key(path.parent.name) not in folders:
                    continue
                match = RESUME_NAME.fullmatch(path.name)
                if match is None or path.suffix.lower() != ".docx":
                    continue
                response = parse_history(docx_text(source.read(name)))
                day = response.response_date
                writer.writerow([match.group(1), "hr-consultant", day or ""])
                observed[day] += 1
        dates = [d for d in observed if d]
        if not dates:
            raise ValueError("В папке консультанта не обнаружено датированных откликов")
        cutoff = max(dates) + timedelta(days=1)
        (directory / "phone_interviews.csv").write_text("interview_key,application_key,held_on,result\n")
        manifest = {
            "input_schema_version": 1, "csv_delimiter": ",", "mode": "work",
            "scope_id": "case-consultant", "scope_label": "Архив кейса · консультант сектора подбора кадров",
            "vacancies": {"hr-consultant": "Консультант сектора подбора кадров"},
            "scope_revision": "1", "timezone": "Europe/Moscow",
            "observed_until": str(cutoff), "extracted_at": f"{date.today()}T12:00:00+03:00",
            "sources": {name: {"source_id": name, "source_revision": "case",
                               "comparable_to_previous_year": False, "complete_intervals": []}
                        for name in ("applications", "phone_interviews")},
        }
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        package = load_package(directory)
        by_year = {}
        versions = {}
        for year in sorted({d.year for d in dates}):
            report = generate(package, year)
            count = sum(observed[d] for d in dates if d.year == year)
            cell = report["totals"]["applications_received"]
            if cell["value"] != count or cell["status"] != "partial":
                raise RuntimeError("Расхождение счётчиков откликов или покрытия")
            if report["totals"]["phone_interviews_held"]["status"] != "unavailable":
                raise RuntimeError("Ошибка покрытия интервью")
            by_year[year] = count
            if output is not None:
                output.mkdir(parents=True, exist_ok=True)
                export(make_workbook(report), output / f"consultant-{year}.xlsx")
            if save_snapshots:
                versions[year] = store.save(report, store.catalogue_dir())
        result = {"files": observed.total(), "undated": observed[None], "dated_by_year": by_year}
        if save_snapshots:
            result["versions"] = versions
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, help="Каталог для агрегированных годовых книг")
    parser.add_argument("--save-snapshots", action="store_true", help="Сохранить рабочие версии в HR_REPORTS_DIR")
    args = parser.parse_args()
    print(json.dumps(check(args.archive, args.output, args.save_snapshots), ensure_ascii=True))
