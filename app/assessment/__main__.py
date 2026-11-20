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
from app.assessment.service import record_llm_calls
from app.assessment.orchestration import assess_in_context
from app.db import repository as repo
from app.db.enums import AuditAction
from app.db.models import (
    Application,
    Candidate,
    Position,
    RequirementProfile,
    Vacancy,
)


class _DeferredClient:
    """Configure the provider only when a model call is actually needed."""
    def __init__(self):
        self.client = None
        self._empty_calls = []

    @property
    def calls(self):
        return self.client.calls if self.client is not None else self._empty_calls

    def model_name(self, role):
        return self.client.model_name(role) if self.client is not None else 'not_called'

    def complete_structured(self, *args, **kwargs):
        if self.client is None:
            self.client = build_client()
        return self.client.complete_structured(*args, **kwargs)


def pick_profile(session: Session, position_code: str, *, technical: bool,
                 profile_id: str | None) -> RequirementProfile:
    position = session.scalar(select(Position).where(Position.code == position_code))
    if position is None:
        raise SystemExit(f"нет должности {position_code}")
    if profile_id:
        profile = session.get(RequirementProfile, uuid.UUID(profile_id))
        if profile is None:
            raise SystemExit(f"нет профиля {profile_id}")
        if profile.position_id != position.id:
            raise SystemExit('profile-id относится к другой должности')
        return profile
    profile = repo.get_approved_profile(session, position.id, synthetic=technical)
    if profile is None:
        kind = "учебного" if technical else "утверждённого"
        raise SystemExit(f"у должности {position_code} нет {kind} профиля требований")
    return profile


def run_one(session_factory, llm: LLMClient, *, candidate_code: str, profile_id: uuid.UUID | None,
            technical: bool, as_of: str | None, purpose='primary', application_id=None,
            expected_position_code=None) -> dict:
    summary = {"candidate_code": candidate_code, "mode": "technical" if technical else "operational",
               "purpose": purpose, "application_id": str(application_id) if application_id else None}
    with session_factory() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.code == candidate_code))
        if candidate is None:
            return summary | {"status": "domain_error", "error": "кандидат не найден"}
        candidate_id = candidate.id
        try:
            manifest = assess_in_context(session, candidate_id=candidate_id, profile_id=profile_id, llm=llm,
                mode=summary['mode'], as_of=as_of, purpose=purpose, application_id=application_id,
                expected_position_code=expected_position_code)
            session.commit()
            return summary | manifest
        except RuleUnsupportedError as error:
            session.rollback()
            outcome = summary | {"status": "rule_unsupported", "error": str(error)}
        except AssessmentDomainError as error:
            session.rollback()
            outcome = summary | {"status": "domain_error", "reason": error.reason, "error": str(error)}
        except LLMError as error:
            session.rollback()
            outcome = summary | {"status": "llm_error", "error": str(error)}
        except repo.RepositoryError as error:
            session.rollback()
            outcome = summary | {'status': 'domain_error', 'reason': 'repository_validation', 'error': str(error)}
    # Вызовы модели остаются в журнале и при ошибке.
    with session_factory() as session:
        if llm.calls:
            record_llm_calls(session, llm, candidate_id)
        repo.write_audit(session, action=AuditAction.OTHER, entity_type='assessment_run',
            entity_id=str(uuid.uuid4()), details=outcome | {'candidate_id': str(candidate_id),
                'profile_id': str(profile_id), 'as_of': as_of})
        session.commit()
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.assessment")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "batch"):
        command = sub.add_parser(name)
        command.add_argument("--position-code",
                             help="run: ожидаемая должность; primary batch: фильтр импортированных вакансий; comparison: целевая должность")
        command.add_argument("--technical", action="store_true", help="учебный профиль, пометка «синтетика»")
        command.add_argument("--profile-id")
        command.add_argument("--as-of", help="месяц расчёта текущего стажа, 'ГГГГ-ММ'")
        command.add_argument('--purpose', choices=['primary', 'comparison'], default='primary',
                             help='primary требует отклик; comparison — явное сравнение с целевой должностью')
        if name == "run":
            command.add_argument("--candidate-code", required=True)
            command.add_argument('--application-id', type=uuid.UUID)
        else:
            command.add_argument("--all-approved", action="store_true",
                                 help="кросс-оценка: выбранные люди × утверждённые профили всех должностей контура")
            command.add_argument("--candidate-code", action="append", dest="candidate_codes",
                                 help="ограничить людей (можно несколько раз)")
            command.add_argument("--limit", type=int, help="не больше N людей")
            command.add_argument("--skip-existing", action="store_true",
                                 help="пары с актуальной оценкой не трогать (без вызова модели и записи)")
            command.add_argument("--workers", type=int, default=1, help="сколько людей оценивать параллельно")
            command.add_argument("--dry-run", action="store_true", help="только показать пары и оценку времени")
    args = parser.parse_args(argv)
    if args.command == "batch" and args.all_approved:
        return _cross_batch(args)
    if args.command == "batch" and not args.position_code:
        parser.error("batch без --all-approved требует --position-code")
    if args.command == 'run' and args.purpose == 'primary' and args.application_id is None:
        parser.error('primary требует --application-id; для отдельного сравнения задайте --purpose comparison')
    if args.purpose == 'comparison' and not args.position_code:
        parser.error('comparison требует --position-code')

    from app.db.session import SessionLocal  # подключение к базе — только при запуске

    llm = _DeferredClient()
    with SessionLocal() as session:
        profile_id = uuid.UUID(args.profile_id) if args.profile_id else None
        if args.purpose == 'comparison':
            profile_id = pick_profile(session, args.position_code, technical=args.technical,
                                      profile_id=args.profile_id).id
        if args.command == "run":
            targets = [(args.candidate_code, args.application_id)]
        else:
            position = session.scalar(select(Position).where(Position.code == args.position_code))
            if position is None:
                parser.error('неизвестная должность импортированных вакансий')
            targets = list(session.execute(
                select(Candidate.code, Application.id).join(Application, Application.candidate_id == Candidate.id)
                .join(Vacancy, Vacancy.id == Application.vacancy_id)
                .where(Vacancy.position_id == position.id, Candidate.is_synthetic == args.technical,
                       Application.source == 'response').order_by(Candidate.code, Application.id)
            ))
    results = [run_one(SessionLocal, llm, candidate_code=code, profile_id=profile_id,
                       technical=args.technical, as_of=args.as_of, purpose=args.purpose, application_id=app_id,
                       expected_position_code=args.position_code if args.command == 'run' else None)
               for code, app_id in targets]
    print(json.dumps(results if args.command == "batch" else results[0], ensure_ascii=False, indent=2))
    return 0 if all(r["status"] in {'ok', 'skipped'} for r in results) else 1


def _cross_batch(args) -> int:
    """batch --all-approved (ai-02): люди по выбору оператора × действующие профили контура."""
    from datetime import UTC, datetime

    from app.assessment.cross import run_cross_batch, select_pairs
    from app.db.session import SessionLocal

    if not (args.candidate_codes or args.limit or args.position_code):
        raise SystemExit("укажите людей: --candidate-code, --limit или --position-code "
                         "(весь архив × 6 профилей — это часы работы модели)")
    as_of = args.as_of or datetime.now(UTC).strftime("%Y-%m")
    with SessionLocal() as session:
        pairs, explained = select_pairs(session, technical=args.technical, candidate_codes=args.candidate_codes,
                                        source_position_code=args.position_code, limit=args.limit)
    plan = {"people": len({p.candidate_id for p in pairs}), "pairs": len(pairs), "explained": explained,
            "estimate_minutes": round(len(pairs) * 10 / 60 / max(args.workers, 1), 1)}
    if args.dry_run or not pairs:
        print(json.dumps(plan | {"pairs_list": [
            {"candidate_code": p.candidate_code, "position_code": p.position_code, "purpose": p.purpose}
            for p in pairs]}, ensure_ascii=False, indent=2))
        return 0
    report = run_cross_batch(SessionLocal, pairs, run_one=run_one, llm_factory=_DeferredClient,
                             technical=args.technical, as_of=as_of, skip_existing=args.skip_existing,
                             workers=args.workers)
    print(json.dumps(report | {"explained": explained}, ensure_ascii=False, indent=2))
    return 0 if "error" not in report["counts"] else 1


if __name__ == "__main__":
    sys.exit(main())
