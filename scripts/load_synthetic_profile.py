"""Загрузить учебный профиль py-9001 (fixtures/assessment/py-9001.json) в базу для живого прогона.

    uv run python -m scripts.load_synthetic_profile

Профиль создаётся учебным (is_synthetic) в статусе draft: утвердить его нельзя, оценивается
он командой `python -m app.assessment run ... --technical`. Повторный запуск создаёт новую версию.
"""
import sys

from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load
from app.db.session import SessionLocal


def main() -> int:
    fixture = load(FIXTURES_DIR / "py-9001.json")
    with SessionLocal() as session:
        profile = create_fixture_profile(session, fixture)
        session.commit()
        print(f"учебный профиль {fixture['profile']['position_code']}: id={profile.id}, "
              f"version={profile.version}, status={profile.status.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
