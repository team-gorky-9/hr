"""Предпросмотр гайда по сохранённой оценке — до появления хранения и HTTP (interview.md v0.1).

    uv run python -m app.interview --candidate-code py-9001 --position-code python-dev [--budget 6] [--no-core]
    uv run python -m app.interview --assessment-id <uuid>

Берёт текущую оценку кандидата по профилю указанной должности (у одного человека их несколько:
первичная по отклику и кросс-оценки), печатает гайд в JSON. Без --position-code допустима только
одна текущая оценка, иначе команда просит уточнить. В базу пишет только журнал вызовов модели.
"""
import argparse
import dataclasses
import json
import sys
import uuid

from sqlalchemy import select

from app.ai import LLMError, build_client
from app.db.models import Assessment, Candidate, Position, RequirementProfile
from app.interview.service import GuideError, build_guide


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.interview")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--candidate-code")
    target.add_argument("--assessment-id", type=uuid.UUID)
    parser.add_argument("--position-code", help="должность профиля оценки (обязательна, если оценок несколько)")
    parser.add_argument("--budget", type=int, default=6)
    parser.add_argument("--no-core", action="store_true", help="без общего ядра (только уточнения)")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    try:
        llm = build_client()
    except LLMError as error:
        print(json.dumps({"status": "llm_error", "error": str(error)}, ensure_ascii=False))
        return 1
    with SessionLocal() as session:
        if args.assessment_id is not None:
            assessment_id = args.assessment_id if session.get(Assessment, args.assessment_id) else None
            options = []
        else:
            query = (select(Assessment.id, Position.code)
                     .join(Candidate, Candidate.id == Assessment.candidate_id)
                     .join(RequirementProfile, RequirementProfile.id == Assessment.profile_id)
                     .join(Position, Position.id == RequirementProfile.position_id)
                     .where(Candidate.code == args.candidate_code, Assessment.is_current))
            if args.position_code:
                query = query.where(Position.code == args.position_code)
            options = session.execute(query.order_by(Position.code)).all()
            assessment_id = options[0][0] if len(options) == 1 else None
        if assessment_id is None:
            if len(options) > 1:
                codes = ", ".join(code for _, code in options)
                print(json.dumps({"status": "position_required",
                                  "error": f"у кандидата несколько текущих оценок ({codes}): укажите --position-code"},
                                 ensure_ascii=False))
            else:
                print(json.dumps({"status": "assessment_required", "error": "нет текущей оценки по этому выбору"},
                                 ensure_ascii=False))
            return 1
        try:
            guide = build_guide(session, assessment_id=assessment_id, llm=llm, budget=args.budget,
                                include_core=not args.no_core)
        except (GuideError, LLMError) as error:
            session.commit()  # журнал вызовов остаётся
            print(json.dumps({"status": getattr(error, "reason", "llm_error"), "error": str(error)}, ensure_ascii=False))
            return 1
        session.commit()
    print(json.dumps({"status": "ok", **dataclasses.asdict(guide)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
