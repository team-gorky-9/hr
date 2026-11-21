"""Короткий HTTP-проход 4C «потребности и возможное покрытие» (wave-4-reporting-stage-1) на учебном пакете.

Нужны база из .env после `alembic upgrade head` и запущенный API. Вход — явно учебный пакет HR ниже
(записи вымышленные), модель и сервисы коллег не нужны.

    uv run python scripts/check_management_plans.py [--base-url http://127.0.0.1:8000]

1) Две потребности и один подтверждённый человек для обеих: номинально 2 из 2, независимо 1 из 2.
2) Добавлен второй подтверждённый человек только для первой потребности и ожидаемый диплом для второй:
   максимальное покрытие 2 из 2 (жадный выбор дал бы 1), диплом виден отдельно и confirmed не меняет.
3) Перечитывание по id и управленческая проекция без имён и оснований; отказ роли department."""
import argparse
import sys

import httpx

PATH = "/api/v1/management/plans"
HR = {"X-User-Login": "hr_demo"}


def need(key, position):
    return {"key": key, "department_key": "economy-training", "position_code": position, "quantity": 1,
            "source_reference": f"Учебная заявка подразделения {key}"}


def person(record, person_id, label):
    return {"person_ref": {"system": "legacy-hr", "id": person_id}, "record_ref": {"system": "legacy-hr", "id": record},
            "label": label, "contact_available": True}


def match(need_key, record, readiness="confirmed", basis="Оценка по утверждённому профилю, подтверждена HR"):
    return {"need_key": need_key, "record_ref": {"system": "legacy-hr", "id": record}, "readiness": readiness,
            "basis": basis + " (учебно)"}


def package(people, matches):
    return {"target_date": "2026-12-01", "scope_label": "Учебный план: отдел экономики", "coverage_note":
            "Учебный пакет HR на одну дату; не полный кадровый учёт", "needs": [
                need("P-1", "economist-training"), need("P-2", "analyst-training")],
            "people": people, "matches": matches}


def show(label, response):
    body = response.json()
    print(f"• {label}: {response.request.method} {response.request.url.path} → {response.status_code}")
    if "result" in body or "totals" in body:
        totals = body.get("result", body).get("totals")
        print(f"   мест {totals['places']}, номинально покрыто потребностей {totals['nominally_covered_needs']},"
              f" независимо мест {totals['independent_covered_places']}, концентрация {totals['concentrated_persons']}")
        for item in body.get("result", body)["needs"]:
            print(f"   {item['key']}: по готовности {item['records_by_readiness']}, подтверждённых людей {item['confirmed_persons']}")
        for warning in body.get("result", body)["warnings"]:
            print(f"   ⚠ {warning['code']}: {warning.get('need_keys') or warning.get('need_key')}")
    else:
        print("  ", body.get("error"))
    return body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    http = httpx.Client(base_url=parser.parse_args(argv).base_url, timeout=30)

    alpha = person("rec-001", "person-A", "Учебный кандидат А")
    first = show("один человек для двух потребностей", http.post(PATH, headers=HR, json=package(
        [alpha], [match("P-1", "rec-001"), match("P-2", "rec-001")])))
    second = show("второй человек и ожидаемый диплом", http.post(PATH, headers=HR, json=package(
        [alpha, person("rec-002", "person-B", "Учебный кандидат Б"), person("rec-003", "person-C", "Учебный выпускник В")],
        [match("P-1", "rec-001"), match("P-2", "rec-001"), match("P-1", "rec-002"),
         match("P-2", "rec-003", "expected", "Диплом ожидается 2026-11-30")])))
    reread = http.get(f"{PATH}/{first['id']}", headers=HR)
    print(f"• перечитать первый снимок: {reread.status_code}, совпадает: {reread.json() == first}")
    summary = show("управленческая проекция", http.get(f"{PATH}/{second['id']}/summary", headers=HR))
    print(f"   имён и record_ref в проекции нет: {'Учебный кандидат' not in str(summary) and 'rec-00' not in str(summary)}")
    show("роль department", http.post(PATH, headers={"X-User-Login": "dept_demo"}, json=package([], [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
