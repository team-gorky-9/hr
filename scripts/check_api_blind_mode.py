"""Проверка API чтения на базе из .env (DATABASE_URL), например на импортированном архиве.

Обходит все маршруты чтения в обоих контурах: списки по каждой вакансии, карточки
откликов, очищенные тексты, а также маршруты чтения Этапа 2 (api.md v0.3): история этапов,
кросс-оценки, резерв, воронка (заголовок X-User-Login: hr_demo из seed). Для каждого ответа ищет в нём значения ПДн этого же
кандидата из candidate_pii (ФИО, телефон, email, ссылки, дата рождения). Город и
гражданство не ищутся: по контракту БД v1.2 они остаются в очищенном тексте.

Печатает только счётчики, время и коды кандидатов с находками — без самих значений ПДн.

    uv run python scripts/check_api_blind_mode.py            # все отклики
    uv run python scripts/check_api_blind_mode.py --limit 200
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models import Candidate, CandidatePii  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

# Ключи с двоеточием: значение "phone" (вид интервью) — не поле ПДн.
HEADERS = {"X-User-Login": "hr_demo"}  # маршрутам Этапа 2 нужен пользователь стенда; Этапу 1 заголовок не мешает
FORBIDDEN_KEYS = ('"raw_text":', '"full_name":', '"birth_date":', '"phone":', '"email":')


def pii_values(pii: CandidatePii) -> list[str]:
    values = [pii.full_name, pii.phone, pii.email, *(pii.links or [])]
    if pii.birth_date:
        values += [pii.birth_date.isoformat(), pii.birth_date.strftime("%d.%m.%Y")]
    # Короткие строки дают ложные совпадения («ФИО 1» внутри «ФИО 12» и т. п. не ищем).
    return [v for v in values if v and len(v) >= 5]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="сколько карточек откликов проверить")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию в cp1251

    with SessionLocal() as session:
        pii_by_candidate = {
            code: pii_values(pii)
            for code, pii in session.execute(
                select(Candidate.code, CandidatePii).join(CandidatePii, CandidatePii.candidate_id == Candidate.id)
            ).all()
        }

    client = TestClient(app)
    findings: list[str] = []
    checked = 0
    timings: dict[str, list[float]] = {"list": [], "detail": [], "text": [], "stage2": []}

    def get(kind: str, url: str, **params) -> dict:
        started = time.perf_counter()
        response = client.get(url, params=params, headers=HEADERS)
        timings[kind].append(time.perf_counter() - started)
        if response.status_code != 200:
            raise SystemExit(f"{url}: HTTP {response.status_code} {response.text[:300]}")
        dumped = json.dumps(response.json(), ensure_ascii=False)
        for key in FORBIDDEN_KEYS:
            if key in dumped:
                findings.append(f"{url}: поле {key}")
        return response.json()

    print("health:", client.get("/api/v1/health").json())
    for contour in ("working", "training"):
        vacancies = get("list", "/api/v1/vacancies", contour=contour)["items"]
        for vacancy in vacancies:
            listing = get("list", f"/api/v1/vacancies/{vacancy['vacancy_id']}/applications", contour=contour)
            statuses: dict[str, int] = {}
            for item in listing["items"]:
                statuses[item["assessment_status"]] = statuses.get(item["assessment_status"], 0) + 1
            print(f"[{contour}] {vacancy['position_code']:<16} откликов {listing['total']:>4}  статусы {statuses}")
            get("stage2", f"/api/v1/positions/{vacancy['position_id']}/reserve", contour=contour)
            for item in listing["items"]:
                if args.limit is not None and checked >= args.limit:
                    break
                checked += 1
                own_pii = pii_by_candidate.get(item["candidate_code"], [])
                bodies = [json.dumps(item, ensure_ascii=False)]
                card = get("detail", f"/api/v1/applications/{item['application_id']}")
                bodies.append(json.dumps(card, ensure_ascii=False))
                if card["candidate"]["current_text_id"]:
                    text = get("text", f"/api/v1/candidate-texts/{card['candidate']['current_text_id']}")
                    bodies.append(json.dumps(text, ensure_ascii=False))
                application_url = f"/api/v1/applications/{item['application_id']}"
                bodies.append(json.dumps(get("stage2", f"{application_url}/history"), ensure_ascii=False))
                cross = get("stage2", f"/api/v1/candidates/{item['candidate_id']}/cross-assessments")
                bodies.append(json.dumps(cross, ensure_ascii=False))
                if any(value in body for value in own_pii for body in bodies):
                    findings.append(f"{item['candidate_code']}: значение ПДн в ответе")

    for contour in ("working", "training"):
        funnel = get("stage2", "/api/v1/analytics/funnel", contour=contour)
        current = {s["code"]: s["current_count"] for s in funnel["stages"] if s["current_count"]}
        print(f"[{contour}] воронка: откликов {funnel['total_applications']}, по этапам {current}")

    def stat(kind: str) -> str:
        values = sorted(timings[kind])
        if not values:
            return "—"
        return f"n={len(values)}, медиана {values[len(values) // 2] * 1000:.0f} мс, макс {values[-1] * 1000:.0f} мс"

    print(f"Проверено карточек откликов: {checked}")
    print(f"Время: списки {stat('list')}; карточки {stat('detail')}; тексты {stat('text')}; Этап 2 {stat('stage2')}")
    print(f"Находок: {len(findings)}")
    for finding in findings[:50]:
        print("  ", finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
