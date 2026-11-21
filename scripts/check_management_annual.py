"""Короткий HTTP-проход 4B «годовой выпуск по доступным фактам» (wave-4-reporting-stage-1).

Нужны база из .env после `alembic upgrade head`, учебные отклики и встречи (например,
scripts/check_management_overview.py --prepare) и запущенный API; каталог выпусков — HR_REPORTS_DIR
сервера. Модель не вызывается.

    uv run python scripts/check_management_annual.py [--base-url …] [--xlsx report.xlsx]

Шаги: выпуск за текущий год (учебный контур, полнота заявлена только для откликов ноября) → JSON →
Excel того же снимка → поздняя поправка (итог открытой встречи py-9106) → новый выпуск, прежний
читается без изменений → отказы."""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from scripts.check_interview_outcome import HR, phone_interview  # noqa: E402

PATH = "/api/v1/management/annual-reports"
MSK = timezone(timedelta(hours=3))


def body(today) -> dict:
    return {"year": today.year, "observed_until": today.isoformat(), "contour": "training",
            "coverage": {"applications": {"complete_intervals": [{"from": f"{today.year}-11-01",
                                                                  "to": today.isoformat()}]}},
            "confirmation_basis": "Учебный журнал legacy-hr; полнота заявлена кадровиком только для откликов ноября"}


def show_release(http: httpx.Client, release: dict) -> dict:
    report = http.get(release["report_url"], headers=HR).json()["report"]
    totals = report["totals"]
    print(f"   snapshot_id={release['snapshot_id'][:16]}… mode={release['mode']} interim={report['interim']}"
          f" период {report['period_start']}…{report['period_end_exclusive']}")
    print(f"   подготовка: {release['preparation']}")
    for name, cell in totals.items():
        print(f"   {name}: {cell['value']} ({cell['status']}, {', '.join(cell['reason_codes']) or '—'})")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--xlsx", type=Path, default=Path("annual-report-check.xlsx"))
    args = parser.parse_args(argv)
    http = httpx.Client(base_url=args.base_url, timeout=60)
    today = datetime.now(MSK).date()

    first = http.post(PATH, headers=HR, json=body(today))
    print(f"• POST {PATH} → {first.status_code}")
    first = first.json()
    report = show_release(http, first)
    xlsx = http.get(first["xlsx_url"], headers=HR)
    args.xlsx.write_bytes(xlsx.content)
    print(f"• GET xlsx → {xlsx.status_code}, {len(xlsx.content)} байт, сохранено в {args.xlsx}")

    _, interview_id = phone_interview("py-9106")
    correction = http.post(f"/api/v1/interviews/{interview_id}/outcome", headers=HR, json={
        "expected_revision": 1, "result": "continue",
        "occurred_at": (datetime.now(MSK) - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0).isoformat(),
        "summary": "Поздняя поправка: разговор вчера внесён сегодня (учебно)"})
    print(f"• поздняя поправка py-9106 → {correction.status_code}")
    second = http.post(PATH, headers=HR, json=body(today)).json()
    print(f"• новый выпуск: другой snapshot_id: {second['snapshot_id'] != first['snapshot_id']}")
    show_release(http, second)
    print(f"• прежний выпуск не изменился: {http.get(first['report_url'], headers=HR).json()['report'] == report}")

    denied = http.post(PATH, headers={"X-User-Login": "dept_demo"}, json=body(today))
    print(f"• роль department → {denied.status_code} {denied.json()['error']['code']}")
    future = http.post(PATH, headers=HR, json=body(today) | {"observed_until": (today + timedelta(days=30)).isoformat()})
    print(f"• observed_until в будущем → {future.status_code} {future.json()['error']['code']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
