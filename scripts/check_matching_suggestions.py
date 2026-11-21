"""Короткий HTTP-проход 3C «подборка HR после публикации» (wave-3-matching-stage-1) на учебных данных.

Нужны база из .env после `alembic upgrade head` и `python -m app.search load-demo`, запущенный API
(`uv run uvicorn app.main:app`). Модель не вызывается, вакансия — предоставленный учебный snapshot.

    uv run python scripts/check_matching_suggestions.py [--base-url http://127.0.0.1:8000]

Последовательность для экрана после публикации: POST /matching/suggestions → показать items →
позже GET /matching/suggestions/{id}. Новая редакция вакансии — новый POST, прежняя подборка остаётся.
Каждый запуск сохраняет две новые подборки (это датированные расчёты, кадровых фактов они не создают)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from scripts.check_matching_candidates import HR, VACANCY  # noqa: E402

PATH = "/api/v1/matching/suggestions"


def show(label: str, response: httpx.Response) -> dict:
    body = response.json()
    print(f"• {label}: {response.request.method} {response.request.url.path} → {response.status_code}")
    if "items" in body:
        print(f"   id={body['id']} vacancy_revision={body['vacancy_revision']} created_at={body['created_at']}"
              f" created_by={body['created_by']['login']}")
        for item in body["items"]:
            fragment = (item["evidence"] or {}).get("fragment") or ""
            print(f"   {item['candidate_code']}: {item['source_status']}, {item['qualification_status']} — «{fragment[:80]}»")
    else:
        print("  ", body.get("error"))
    return body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    http = httpx.Client(base_url=parser.parse_args(argv).base_url, timeout=30)

    first = show("подборка после публикации, ред. 1", http.post(PATH, headers=HR, json={"vacancy": VACANCY, "limit": 3}))
    reread = http.get(f"{PATH}/{first['id']}", headers=HR)
    print(f"• перечитать по id: {reread.status_code}, совпадает с созданной: {reread.json() == first}")
    edited = VACANCY | {"revision": 2, "observed_at": "2026-11-22T09:00:00+03:00",
                        "search_query": "функциональные требования к СЭД"}
    second = show("новая редакция вакансии, ред. 2", http.post(PATH, headers=HR, json={"vacancy": edited, "limit": 3}))
    print(f"• две подборки: {first['id'] != second['id']}, первая не изменилась: "
          f"{http.get(f'{PATH}/{first['id']}', headers=HR).json() == first}")
    show("закрытая вакансия", http.post(PATH, headers=HR, json={"vacancy": VACANCY | {"status": "closed"}}))
    show("роль department читает подборку", http.get(f"{PATH}/{first['id']}", headers={"X-User-Login": "dept_demo"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
