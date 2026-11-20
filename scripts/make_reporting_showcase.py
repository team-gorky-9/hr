"""Create a deterministic, entirely synthetic two-year municipal reporting package."""
import argparse
import calendar
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from random import Random

VACANCIES = {"services": "Специалист по обращениям", "finance": "Финансовый аналитик",
             "it": "Инженер информационных систем", "hr": "Консультант по кадрам"}
DEPARTMENTS = {"services": "Городские сервисы", "finance": "Финансовое управление",
               "it": "Цифровое развитие", "hr": "Кадровая политика"}


def create(directory: Path):
    directory.mkdir(parents=True, exist_ok=False)
    rng = Random(202511)
    period = [{"from": "2024-01-01", "to": "2026-02-01"}]
    scope = {"scope_id": "training-administration", "scope_revision": "1", "mode": "demo"}
    def source(name):
        return {"source_id": name, "source_revision": "training-1", "complete_intervals": period}
    def json_file(name, value):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    def write_rows(name, header, data):
        with (directory / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header.split(","))
            writer.writerows(data)

    json_file("manifest.json", {**scope, "input_schema_version": 1, "scope_label": "Учебная администрация",
              "csv_delimiter": ",", "timezone": "Europe/Moscow", "observed_until": "2026-02-01",
              "extracted_at": "2026-02-02T09:00:00+03:00", "vacancies": VACANCIES,
              "sources": {name: {**source(name), "comparable_to_previous_year": True}
                          for name in ("applications", "phone_interviews")}})
    json_file("operations.json", {**scope, "schema_version": 1, "departments": DEPARTMENTS,
              "sources": {"workforce": source("workforce"),
                          "handoffs": {**source("handoffs"), "includes_opening_balance": True}}})
    apps, calls, transfers, staff = [], [], [], []
    people = dict(zip(DEPARTMENTS, (41, 24, 32, 15)))
    for year in (2024, 2025):
        for month in range(1, 13):
            for i, key in enumerate(VACANCIES):
                count = 10 + i * 3 + rng.randrange(8) + (4 if year == 2025 else 0)
                if year == 2025 and key == "services" and month == 9:
                    count += 43
                hires, exits = rng.randrange(3), rng.randrange(3)
                people[key] += hires - exits
                staff.append([f"{year}-{month:02d}", key, people[key] + 3 + i, people[key] - 0.5,
                              people[key], hires, exits])
                for _ in range(count):
                    day = date(year, month, rng.randint(1, calendar.monthrange(year, month)[1]))
                    app = f"A{len(apps) + 1}"
                    apps.append([app, key, day])
                    if rng.random() < 0.32:
                        continue
                    first = day + timedelta(days=rng.randint(1, 10 if key != "it" else 21))
                    outcome = rng.choice(["continue", "continue", "stop", "pending"])
                    calls.append([f"C{len(calls) + 1}", app, first, outcome])
                    if rng.random() < 0.18:
                        calls.append([f"C{len(calls) + 1}", app, first + timedelta(days=2), "continue"])
                    if outcome == "continue":
                        sent = first + timedelta(days=1)
                        answer = sent + timedelta(days=rng.randint(1, 24 if key == "it" else 12))
                        unresolved = (year == 2025 and month == 12 and rng.random() < 0.35)
                        transfers.append([f"T{len(transfers) + 1}", key, sent,
                                          "" if unresolved or answer >= date(2026, 2, 1) else answer])
    write_rows("applications.csv", "application_key,vacancy_key,applied_on", apps)
    write_rows("phone_interviews.csv", "interview_key,application_key,held_on,result", calls)
    write_rows("workforce.csv", "month,department_key,authorized_fte,occupied_fte,headcount,hires,exits", staff)
    write_rows("handoffs.csv", "handoff_key,department_key,sent_on,answered_on", transfers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_directory", type=Path)
    create(parser.parse_args().new_directory)
