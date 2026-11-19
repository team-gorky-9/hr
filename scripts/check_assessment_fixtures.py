"""Проверить контрольный набор оценки без базы и без модели.

Печатает по каждому случаю: кто отвечает за ожидание (schema / db_v1 / stage_1),
наблюдаемый итог и проблемы. Код выхода 1, если набор противоречит сам себе
или правилам app/assessment/verification.py.

Запуск (из корня hr):
    uv run python -m scripts.check_assessment_fixtures
    uv run python -m scripts.check_assessment_fixtures fixtures/assessment/py-9001.json
"""
import sys
from pathlib import Path

from app.assessment.fixtures import check_fixture, fixture_paths, load


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] or fixture_paths()
    if not paths:
        print("нет файлов набора в fixtures/assessment")
        return 1
    failed = False
    for path in paths:
        fixture = load(path)
        common, reports = check_fixture(fixture)
        print(f"{path} · синтетика: {'да' if fixture['synthetic'] else 'НЕТ'} · случаев: {len(reports)}")
        for problem in common:
            failed = True
            print(f"  ! {problem}")
        for report in reports:
            status = "ok  " if report.ok else "FAIL"
            outcome = report.observed.get("refusal") or report.observed.get("formal_result") or "ошибка схемы"
            print(f"  {status} {report.case_id:<32} {report.enforced_by:<8} итог: {outcome}")
            for problem in report.problems:
                failed = True
                print(f"       ! {problem}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
