"""Короткий HTTP-проход 4A «текущая работа и факты интервью» (wave-4-reporting-stage-1) на учебных данных.

Нужны база из .env после `alembic upgrade head`, учебные отклики (`python -m scripts.demo_setup --no-llm`)
и запущенный API. Модель не вызывается.

    uv run python scripts/check_management_overview.py --prepare   # учебные встречи: continue, no_answer, открытая
    uv run python scripts/check_management_overview.py             # GET /management/overview за два соседних дня

Подготовка использует штатные операции: repo.open_interview и POST /interviews/{id}/outcome второй волны.
Повторный --prepare ничего не дублирует: завершённые встречи остаются, открытая встреча одна на отклик."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from scripts.check_interview_outcome import HR, phone_interview  # noqa: E402

PATH = "/api/v1/management/overview"
PLAN = (("py-9103", "continue", "2026-11-20T23:59:00+03:00"),   # последний день периода — входит
        ("py-9104", "no_answer", "2026-11-20T10:00:00+03:00"),
        ("py-9105", "stop", "2026-11-21T00:00:00+03:00"))       # следующий день — в период 20.11 не входит
OPEN = "py-9106"


def prepare(http: httpx.Client) -> None:
    for code, result, when in PLAN:
        _, interview_id = phone_interview(code)
        response = http.post(f"/api/v1/interviews/{interview_id}/outcome", headers=HR, json={
            "expected_revision": 1, "result": result, "occurred_at": when, "summary": "Учебный итог для сводки"})
        print(f"• {code} {result} {when}: {response.status_code}"
              f"{' (уже записан ранее)' if response.status_code == 409 else ''}")
    _, interview_id = phone_interview(OPEN)
    print(f"• {OPEN}: открытая встреча {interview_id}")


def show(http: httpx.Client, period_from: str, period_to: str) -> None:
    response = http.get(PATH, headers=HR, params={"from": period_from, "to": period_to, "contour": "training"})
    body = response.json()
    block = body["interviews"]
    print(f"• GET {PATH}?from={period_from}&to={period_to}&contour=training → {response.status_code}")
    print(f"   held={block['held_count']} (откликов {block['held_applications_count']}) no_answer={block['no_answer_count']}"
          f" open={block['open_count']} undated={block['undated_count']}")
    for row in block["by_interviewer"]:
        print(f"   {row['login']}: held={row['held_count']} no_answer={row['no_answer_count']} outcomes={row['outcomes']}")
    print(f"   воронка: откликов {body['funnel']['total_applications']}, срез {body['funnel']['as_of']}")
    print("   источники:", ", ".join(f"{s['key']}={s['status']}" for s in body["sources"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args(argv)
    http = httpx.Client(base_url=args.base_url, timeout=30)
    if args.prepare:
        prepare(http)
        return 0
    show(http, "2026-11-20", "2026-11-21")
    show(http, "2026-11-21", "2026-11-22")
    denied = http.get(PATH, headers={"X-User-Login": "dept_demo"},
                      params={"from": "2026-11-20", "to": "2026-11-21", "contour": "training"})
    print(f"• роль department: {denied.status_code} {denied.json()['error']['code']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
