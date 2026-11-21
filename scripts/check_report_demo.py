"""Волна 6 · факты, показатель и Excel: короткий выпуск годового отчёта на маленьком учебном наборе.

Учебный набор (только синтетика, отдельная пустая база):
- 4 отклика площадки на python-dev: 2026-09-15, 2026-11-03, 2026-11-10, 2026-11-12;
- телефонные встречи: continue 2026-11-05, no_answer 2026-11-11, одна открытая.

    createdb hr_report && DATABASE_URL=…/hr_report uv run alembic upgrade head
    DATABASE_URL=…/hr_report uv run python scripts/check_report_demo.py --prepare      # набор + итоги встреч
    DATABASE_URL=…/hr_report HR_REPORTS_DIR=… uv run uvicorn app.main:app --port 8000 &
    DATABASE_URL=…/hr_report uv run python scripts/check_report_demo.py --transcript docs/reports/wave-6-report-demo.transcript.json \
        --xlsx docs/reports/wave-6-report-demo.xlsx

Выпуск: год 2026, observed_until=2026-11-21. Полнота заявлена только для откликов (2026-09-01…2026-11-21);
для телефонных встреч полнота не заявлена — источник виден как неполный, а не как ноль. Затем поздняя
поправка (итог ещё одной встречи) и новый выпуск; прежний снимок читается без изменений.
Итоги встреч записываются штатной операцией POST /interviews/{id}/outcome (через HTTP при прогоне)."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import repository as repo  # noqa: E402
from app.db.enums import ApplicationSource, Channel, DocumentKind, FileFormat  # noqa: E402
from app.db.models import Application, Candidate, Position, Vacancy  # noqa: E402
from app.db.seed import seed_all  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

HR = {"X-User-Login": "hr_demo"}
APPLIED = (("rep-9001", date(2026, 9, 15)), ("rep-9002", date(2026, 11, 3)),
           ("rep-9003", date(2026, 11, 10)), ("rep-9004", date(2026, 11, 12)))
BODY = {"year": 2026, "observed_until": "2026-11-21", "contour": "training",
        "coverage": {"applications": {"complete_intervals": [{"from": "2026-09-01", "to": "2026-11-21"}],
                                      "comparable_to_previous_year": False}},
        "confirmation_basis": "Учебный набор волны 6: полнота заявлена только для откликов с 01.09.2026 (учебно)"}


def prepare() -> None:
    with SessionLocal() as session:
        seed_all(session)
        vacancy = session.scalar(select(Vacancy).join(Position).where(Position.code == "python-dev").limit(1))
        for code, applied_on in APPLIED:
            if session.scalar(select(Candidate).where(Candidate.code == code)) is not None:
                continue
            text = f"Учебное резюме {code}: разработка на Python (синтетика)"
            document, _ = repo.add_source_document(
                session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.TXT,
                original_path=f"Синтетика/{code}.txt", raw_text=text)
            candidate = repo.create_candidate(session, code=code, source_document_id=document.id, redacted_text=text,
                                              redaction_method="synthetic", is_synthetic=True)
            application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                                  vacancy_id=vacancy.id, applied_at=applied_on)
            repo.open_interview(session, application.id, "phone")
        session.commit()
    print("учебный набор: 4 отклика, 4 открытые телефонные встречи")


def interview_of(code: str) -> str:
    with SessionLocal() as session:
        application_id = session.scalar(select(Application.id).join(Candidate).where(Candidate.code == code))
        return str(repo.latest_interview(session, application_id, "phone").id)


class Recorder:
    def __init__(self, base_url):
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=60)
        self.steps = []

    def call(self, step, login, method, path, body=None, keep_body=True):
        response = self.http.request(method, path, headers={"X-User-Login": login}, json=body)
        json_body = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
        if json_body and isinstance(json_body, dict) and "report" in json_body:
            # В transcript — заголовок выпуска и ключевые ячейки; полный снимок читается по report_url.
            report = json_body["report"]
            json_body = {"release": json_body["release"], "report_excerpt": {
                k: report[k] for k in ("snapshot_id", "year", "mode", "period_start", "period_end_exclusive",
                                       "interim", "sources", "quality", "totals")} | {
                "months": [m for m in report["months"] if m["month"] in ("2026-09", "2026-10", "2026-11")]}}
        self.steps.append({"step": step, "actor": login, "method": method, "path": path, "request": body,
                           "status": response.status_code,
                           "response": json_body if keep_body else {"content_type": response.headers.get("content-type"),
                                                                    "bytes": len(response.content)}})
        print(f"{'✓' if response.status_code < 400 else '✗'} {step}: {method} {path} → {response.status_code}")
        return response


def outcome(rec, step, code, result, when):
    return rec.call(step, "hr_demo", "POST", f"/api/v1/interviews/{interview_of(code)}/outcome", {
        "expected_revision": 1, "result": result, "occurred_at": when, "summary": "Учебный итог встречи (волна 6)"})


def cell(report, month, metric):
    item = next(m for m in report["months"] if m["month"] == month)["metrics"][metric]
    return f"{item['value']} ({item['status']}{', ' + ', '.join(item['reason_codes']) if item['reason_codes'] else ''})"


def run(base_url: str, xlsx: Path | None) -> dict:
    rec = Recorder(base_url)
    outcome(rec, "Итог встречи rep-9002: continue 05.11", "rep-9002", "continue", "2026-11-05T14:00:00+03:00")
    outcome(rec, "Итог встречи rep-9003: no_answer 11.11", "rep-9003", "no_answer", "2026-11-11T10:00:00+03:00")
    first = rec.call("Выпуск отчёта 2026", "hr_demo", "POST", "/api/v1/management/annual-reports", BODY).json()
    report = rec.call("Чтение того же снимка", "hr_demo", "GET", first["report_url"]).json()["report"]
    excel = rec.call("Excel того же снимка", "hr_demo", "GET", first["xlsx_url"], keep_body=False)
    if xlsx:
        xlsx.write_bytes(excel.content)
    reread = rec.http.get(first["report_url"], headers=HR).json()["report"]
    print(f"• перечитывание совпадает: {reread == report}")
    print("• показатель applications_received:")
    for month in ("2026-09", "2026-10", "2026-11"):
        print(f"   {month}: отклики {cell(report, month, 'applications_received')}, "
              f"разговоры {cell(report, month, 'phone_interviews_held')}")
    print(f"   год: {report['totals']['applications_received']}")

    outcome(rec, "Поздняя поправка: итог встречи rep-9004 continue 12.11", "rep-9004", "continue",
            "2026-11-12T16:00:00+03:00")
    second = rec.call("Новый выпуск после поправки", "hr_demo", "POST", "/api/v1/management/annual-reports", BODY).json()
    report2 = rec.call("Чтение нового снимка", "hr_demo", "GET", second["report_url"]).json()["report"]
    old_again = rec.http.get(first["report_url"], headers=HR).json()["report"]
    print(f"• новый snapshot_id: {second['snapshot_id'] != first['snapshot_id']}, прежний не изменился: {old_again == report}")
    print(f"   разговоры 2026-11: было {cell(report, '2026-11', 'phone_interviews_held')}, "
          f"стало {cell(report2, '2026-11', 'phone_interviews_held')}")
    rec.call("Отказ: роль department", "dept_demo", "POST", "/api/v1/management/annual-reports", BODY)
    rec.call("Отказ: полнота за пределами наблюдения", "hr_demo", "POST", "/api/v1/management/annual-reports",
             BODY | {"coverage": {"applications": {"complete_intervals": [{"from": "2026-09-01", "to": "2026-12-01"}]}}})
    return {"first": first, "second": second, "steps": rec.steps}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--xlsx", type=Path)
    args = parser.parse_args(argv)
    if args.prepare:
        prepare()
        return 0
    result = run(args.base_url, args.xlsx)
    if args.transcript:
        args.transcript.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"transcript: {args.transcript}")
    print(json.dumps({k: {"snapshot_id": v["snapshot_id"], "report_url": v["report_url"]} for k, v in result.items()
                      if k != "steps"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
