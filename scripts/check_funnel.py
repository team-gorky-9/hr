"""Сверка GET /api/v1/analytics/funnel с прямыми SQL-счётчиками на базе из .env (DATABASE_URL).

Для каждого контура и каждой вакансии (и без фильтра) сравнивает ответ API с независимыми
запросами к applications и stage_events. Печатает расхождения; код выхода 1, если они есть.

    uv run python scripts/check_funnel.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

SCOPE = """
    FROM applications a
    JOIN candidates c ON c.id = a.candidate_id
    WHERE a.source = 'response' AND a.vacancy_id IS NOT NULL
      AND c.is_synthetic = :synthetic AND (CAST(:vacancy_id AS uuid) IS NULL OR a.vacancy_id = CAST(:vacancy_id AS uuid))
"""


def sql_counts(session, synthetic: bool, vacancy_id: str | None) -> dict:
    params = {"synthetic": synthetic, "vacancy_id": vacancy_id}
    total = session.execute(text(f"SELECT count(*) {SCOPE}"), params).scalar_one()
    current = dict(session.execute(text(f"SELECT a.current_stage_code, count(*) {SCOPE} GROUP BY 1"), params).all())
    reached = dict(session.execute(text(
        f"SELECT e.to_stage_code, count(DISTINCT e.application_id) FROM stage_events e "
        f"WHERE e.application_id IN (SELECT a.id {SCOPE}) GROUP BY 1"), params).all())
    return {"total": total, "current": current, "reached": reached}


def api_counts(funnel: dict) -> dict:
    return {
        "total": funnel["total_applications"],
        "current": {s["code"]: s["current_count"] for s in funnel["stages"] if s["current_count"]},
        "reached": {s["code"]: s["reached_count"] for s in funnel["stages"] if s["reached_count"]},
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    client = TestClient(app)
    mismatches = 0
    with SessionLocal() as session:
        vacancy_ids = [str(v) for v in session.execute(text("SELECT id FROM vacancies ORDER BY title")).scalars()]
        for contour, synthetic in (("working", False), ("training", True)):
            for vacancy_id in [None, *vacancy_ids]:
                params = {"contour": contour} | ({"vacancy_id": vacancy_id} if vacancy_id else {})
                api = api_counts(client.get("/api/v1/analytics/funnel", params=params,
                                            headers={"X-User-Login": "hr_demo"}).json())
                db = sql_counts(session, synthetic, vacancy_id)
                status = "ok" if api == db else "РАСХОЖДЕНИЕ"
                mismatches += api != db
                print(f"[{contour}] {vacancy_id or 'все вакансии':<36} откликов {db['total']:>5}  {status}")
                if api != db:
                    print("   API:", api, "\n   SQL:", db)
    print(f"Расхождений: {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
