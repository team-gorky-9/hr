"""CLI оценивания (контракт assessment.md, п. 5).

    uv run python -m app.assessment run --candidate-code py-9001 --position-code python-dev --technical --as-of 2026-11
    uv run python -m app.assessment batch --position-code python-dev --technical

Транзакция на каждого кандидата: ошибка одного не откатывает остальных. Вызовы модели
записываются в audit_log и при ошибке (отдельной транзакцией после отката).
Печатает JSON-сводку; текста резюме в выводе нет.
"""
import argparse
import json
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import LLMClient, LLMError, build_client
from app.assessment.errors import AssessmentDomainError, RuleUnsupportedError
from app.assessment.service import assess_candidate, record_llm_calls
from app.db import repository as repo
from app.db.enums import RequirementStatus
from app.db.models import (
    Application,
    Assessment,
    Candidate,
    Position,
    RequirementProfile,
    Vacancy,
)


def pick_profile(session: Session, position_code: str, *, technical: bool,
                 profile_id: str | None) -> RequirementProfile:
    """Профиль для оценки. Явный --profile-id берётся как есть (правила режима проверит сервис);
    иначе действующий профиль своего контура через repository.get_approved_profile,
    а в --technical при его отсутствии — последний учебный черновик."""
    if profile_id:
        profile = session.get(RequirementProfile, uuid.UUID(profile_id))
        if profile is None:
            raise SystemExit(f"нет профиля {profile_id}")
        return profile
    position = session.scalar(select(Position).where(Position.code == position_code))
    if position is None:
        raise SystemExit(f"нет должности {position_code}")
    profile = repo.get_approved_profile(session, position.id, synthetic=technical)
    if profile is None and technical:
        # Учебного кандидата можно оценивать и по учебному черновику: берём последнюю версию.
        profile = session.scalars(
            select(RequirementProfile).where(RequirementProfile.position_id == position.id,
                                             RequirementProfile.is_synthetic,
                                             RequirementProfile.status == RequirementStatus.DRAFT)
            .order_by(RequirementProfile.version.desc())
        ).first()
    if profile is None:
        kind = "учебного" if technical else "рабочего"
        raise SystemExit(f"у должности {position_code} нет утверждённого {kind} профиля; "
                         "любой не архивный профиль можно указать через --profile-id (только --technical)")
    return profile


def run_one(session_factory, llm: LLMClient, *, candidate_code: str, profile_id: uuid.UUID,
            technical: bool, as_of: str | None) -> dict:
    summary = {"candidate_code": candidate_code, "mode": "technical" if technical else "operational"}
    with session_factory() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.code == candidate_code))
        if candidate is None:
            return summary | {"status": "domain_error", "error": "кандидат не найден"}
        candidate_id = candidate.id
        try:
            assessment_id = assess_candidate(session, candidate_id=candidate_id, profile_id=profile_id, llm=llm,
                                             mode=summary["mode"], as_of=as_of)
            assessment = session.get(Assessment, assessment_id)
            session.commit()
            return summary | {"status": "ok", "card_id": str(assessment.card_id), "assessment_id": str(assessment_id),
                              "formal_result": assessment.formal_result.value, "summary": assessment.summary}
        except RuleUnsupportedError as error:
            session.rollback()
            outcome = summary | {"status": "rule_unsupported", "error": str(error)}
        except AssessmentDomainError as error:
            session.rollback()
            outcome = summary | {"status": "domain_error", "reason": error.reason, "error": str(error)}
        except LLMError as error:
            session.rollback()
            outcome = summary | {"status": "llm_error", "error": str(error)}
    # Вызовы модели остаются в журнале и при ошибке.
    if llm.calls:
        with session_factory() as session:
            record_llm_calls(session, llm, candidate_id)
            session.commit()
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.assessment")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "batch"):
        command = sub.add_parser(name)
        command.add_argument("--position-code", required=True)
        command.add_argument("--technical", action="store_true", help="учебный профиль, пометка «синтетика»")
        command.add_argument("--profile-id")
        command.add_argument("--as-of", help="месяц расчёта текущего стажа, 'ГГГГ-ММ'")
        if name == "run":
            command.add_argument("--candidate-code", required=True)
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal  # подключение к базе — только при запуске

    try:
        llm = build_client()
    except LLMError as error:
        print(json.dumps({"status": "llm_error", "error": str(error)}, ensure_ascii=False))
        return 1
    with SessionLocal() as session:
        profile = pick_profile(session, args.position_code, technical=args.technical, profile_id=args.profile_id)
        profile_id = profile.id
        if args.command == "run":
            codes = [args.candidate_code]
        else:
            codes = list(session.scalars(
                select(Candidate.code).join(Application, Application.candidate_id == Candidate.id)
                .join(Vacancy, Vacancy.id == Application.vacancy_id)
                .where(Vacancy.position_id == profile.position_id,
                       Candidate.is_synthetic.is_(args.technical))  # свой контур
                .distinct().order_by(Candidate.code)
            ))
    results = [run_one(SessionLocal, llm, candidate_code=code, profile_id=profile_id,
                       technical=args.technical, as_of=args.as_of) for code in codes]
    print(json.dumps(results if args.command == "batch" else results[0], ensure_ascii=False, indent=2))
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
