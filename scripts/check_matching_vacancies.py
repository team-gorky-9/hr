"""Короткий HTTP-проход 3B «вакансии по присланному резюме» (wave-3-matching-stage-1) на учебных данных.

Запускать на ОТДЕЛЬНОЙ пустой учебной базе: подготовка утверждает учебные профили-копии
fixtures/assessment/py-9001.json на python-dev, qa-manual и frontend-dev и этим заменяет действующие
учебные профили этих должностей. Модель не вызывается — оценки пишет FakeLLMClient, как в тестах.

    createdb hr_match && DATABASE_URL=…/hr_match uv run alembic upgrade head
    DATABASE_URL=…/hr_match uv run python scripts/check_matching_vacancies.py --prepare   # данные
    DATABASE_URL=…/hr_match uv run uvicorn app.main:app &                                 # API
    DATABASE_URL=…/hr_match uv run python scripts/check_matching_vacancies.py             # проход

Кандидат match-9001: python-dev — met, qa-manual — unknown (нет сведений о стаже), frontend-dev
утверждён без оценки, четвёртая вакансия закрыта."""
import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.ai import FakeLLMClient  # noqa: E402
from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load  # noqa: E402
from app.assessment.service import assess_candidate  # noqa: E402
from app.db import repository as repo  # noqa: E402
from app.db.enums import Channel, DocumentKind, FileFormat  # noqa: E402
from app.db.models import Candidate, Position, User  # noqa: E402
from app.db.seed import seed_all  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

PATH = "/api/v1/matching/vacancies"
HR = {"X-User-Login": "hr_demo"}
CODE = "match-9001"
FIXTURE = load(FIXTURES_DIR / "py-9001.json")
INDICATOR = FIXTURE["profile"]["competencies"][0]["indicators"][0]["key"]
TEXT = "Написал API-тесты для сервиса заявок.\nОбщий коммерческий опыт — 3 года."
POSITIONS = ("python-dev", "qa-manual", "frontend-dev")


def model(statement: str | None):
    """Учебная модель оценки: со statement стаж подтверждён (met), без него — unknown."""
    def respond(role, schema, system, user):
        if schema == "CandidateCard":
            return {"missing": [] if statement else ["длительность коммерческого опыта"]}
        if schema == "FormalExtraction":
            return {"statement": {"years": 3, "commercial": True, "quote": statement}} if statement else {}
        return {"indicators": [{"indicator_key": INDICATOR, "status": "confirmed", "quote": "Написал API-тесты"}]}
    return FakeLLMClient(respond)


def prepare() -> None:
    with SessionLocal() as session:
        seed_all(session)
        if session.scalar(select(Candidate).where(Candidate.code == CODE)) is not None:
            print("данные уже подготовлены")
            return
        approver = session.scalar(select(User).where(User.login == "hr_demo"))
        profiles = {}
        for code in POSITIONS:
            fixture = copy.deepcopy(FIXTURE)
            fixture["profile"]["position_code"] = code
            draft = create_fixture_profile(session, fixture)
            profiles[code] = repo.approve_requirement_profile(
                session, draft.id, approved_by_user_id=approver.id,
                approval_basis="Учебная копия py-9001 для проверки 3B, не кадровое утверждение")
        document, _ = repo.add_source_document(
            session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.TXT,
            original_path=f"Синтетика/{CODE}.txt", raw_text=TEXT)
        candidate = repo.create_candidate(session, code=CODE, source_document_id=document.id, redacted_text=TEXT,
                                          redaction_method="synthetic", is_synthetic=True)
        assess_candidate(session, candidate_id=candidate.id, profile_id=profiles["python-dev"].id,
                         llm=model("Общий коммерческий опыт — 3 года."), mode="technical", as_of="2026-11")
        assess_candidate(session, candidate_id=candidate.id, profile_id=profiles["qa-manual"].id,
                         llm=model(None), mode="technical", as_of="2026-11")
        session.commit()
        print(f"подготовлен {CODE}: оценки python-dev и qa-manual, frontend-dev без оценки")


def snapshot(number: int, code: str, profile, **changes) -> dict:
    return {
        "ref": {"system": "legacy-hr", "id": f"00000000-0000-4000-8000-0000000000b{number}"}, "revision": 1,
        "title": f"Учебная вакансия {code}", "description": "Учебное объявление", "position_code": code,
        "status": "published", "contour": "training", "observed_at": "2026-11-21T09:00:00+03:00",
        "profile_ref": {"system": "legacy-hr", "id": str(profile.id), "version": profile.version},
    } | changes


def run(base_url: str) -> None:
    with SessionLocal() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.code == CODE))
        if candidate is None:
            raise SystemExit("сначала --prepare")
        profiles = {code: repo.get_approved_profile(session, session.scalar(
            select(Position.id).where(Position.code == code)), synthetic=True) for code in POSITIONS}
        candidate_id = str(candidate.id)
    body = {"candidate_id": candidate_id, "contour": "training", "vacancies": [
        snapshot(1, "qa-manual", profiles["qa-manual"]), snapshot(2, "python-dev", profiles["python-dev"]),
        snapshot(3, "frontend-dev", profiles["frontend-dev"]),
        snapshot(4, "python-dev", profiles["python-dev"], status="closed")]}
    http = httpx.Client(base_url=base_url, timeout=30)
    response = http.post(PATH, headers=HR, json=body)
    result = response.json()
    print(f"• POST {PATH} {CODE}: {response.status_code}, source_mode={result['source_mode']}")
    for item in result["items"]:
        print(f"  item  …{item['vacancy_ref']['id'][-2:]} {item['title']}: {item['formal_result']} — {item['reason']}")
    for item in result["needs_evaluation"]:
        print(f"  needs …{item['vacancy_ref']['id'][-2:]} {item['title']}: {item['reason']}")
    for item in result["excluded"]:
        print(f"  excl  …{item['vacancy_ref']['id'][-2:]}: {item['reason']}")
    denied = http.post(PATH, headers={"X-User-Login": "dept_demo"}, json=body)
    print(f"• роль department: {denied.status_code} {denied.json()['error']['code']}")
    working = http.post(PATH, headers=HR, json=body | {"contour": "working"})
    print(f"• рабочий контур без ключа поиска: {working.status_code} {working.json()['error']['code']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--prepare", action="store_true", help="подготовить учебные профили и оценки (без модели)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    prepare() if args.prepare else run(args.base_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
