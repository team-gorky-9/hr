"""Короткий HTTP-проход 3A «люди под выбранную вакансию» (wave-3-matching-stage-1) на учебных данных.

Нужны база из .env после `alembic upgrade head` и `python -m app.search load-demo`, запущенный API
(`uv run uvicorn app.main:app`). Модель не вызывается. Вакансия — предоставленный учебный snapshot
(source_mode=provided), сервис вакансий не нужен.

    uv run python scripts/check_matching_candidates.py [--base-url http://127.0.0.1:8000]

Шаги: запрос про требования к ИС → известный фрагмент; добавлен отсутствующий обязательный термин →
пустая выдача; закрытая вакансия → 409; рабочий контур без ключа поиска → 401; роль department → 403;
если в базе есть утверждённый учебный профиль python-dev — статус оценки по точному профилю."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import repository as repo  # noqa: E402
from app.db.models import Position  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

PATH = "/api/v1/matching/candidates"
HR = {"X-User-Login": "hr_demo"}
VACANCY = {
    "ref": {"system": "legacy-hr", "id": "00000000-0000-4000-8000-0000000000a1"}, "revision": 1,
    "title": "Аналитик информационных систем (учебная)",
    "description": "Учебное объявление: анализ требований к информационным системам администрации, "
                   "согласование с подрядчиком, описание сценариев.",
    "position_code": "analyst-training", "status": "published", "contour": "training",
    "observed_at": "2026-11-21T09:00:00+03:00", "profile_ref": None,
    "search_query": "анализ и согласование требований к ИС",
}


def show(label: str, response: httpx.Response) -> dict:
    body = response.json()
    print(f"• {label}: {response.status_code}")
    if "items" in body:
        print(f"   source_mode={body['source_mode']} observed_at={body['observed_at']} items={len(body['items'])}")
        for item in body["items"][:3]:
            fragment = (item["evidence"] or {}).get("fragment", "")
            print(f"   {item['candidate_code']}: {item['qualification_status']}/{item['qualification_reason']}"
                  f" — «{fragment[:90]}»")
    else:
        print("  ", body.get("error"))
    return body


def python_profile_ref() -> dict | None:
    with SessionLocal() as session:
        position = session.scalar(select(Position).where(Position.code == "python-dev"))
        profile = repo.get_approved_profile(session, position.id, synthetic=True) if position else None
        return {"system": "legacy-hr", "id": str(profile.id), "version": profile.version} if profile else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    http = httpx.Client(base_url=parser.parse_args(argv).base_url, timeout=30)

    show("вакансия + запрос про требования к ИС", http.post(PATH, headers=HR, json={"vacancy": VACANCY, "limit": 3}))
    show("+ отсутствующий обязательный термин", http.post(PATH, headers=HR, json={
        "vacancy": VACANCY, "filters": {"required_terms": ["SAP ERP"]}}))
    show("закрытая вакансия", http.post(PATH, headers=HR, json={"vacancy": VACANCY | {"status": "closed"}}))
    show("рабочий контур без ключа поиска", http.post(PATH, headers=HR, json={"vacancy": VACANCY | {"contour": "working"}}))
    show("роль department", http.post(PATH, headers={"X-User-Login": "dept_demo"}, json={"vacancy": VACANCY}))
    ref = python_profile_ref()
    if ref:
        show("python-dev с точным профилем", http.post(PATH, headers=HR, json={"vacancy": VACANCY | {
            "position_code": "python-dev", "search_query": "Python", "profile_ref": ref}, "limit": 5}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
