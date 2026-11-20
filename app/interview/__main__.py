"""Предпросмотр гайда по сохранённой оценке — до появления хранения и HTTP (interview.md v0.1).

    uv run python -m app.interview --candidate-code py-9001 [--budget 6] [--no-core]

Берёт текущую оценку кандидата, печатает гайд в JSON. В базу пишет только журнал вызовов модели.
"""
import argparse
import dataclasses
import json
import sys

from sqlalchemy import select

from app.ai import LLMError, build_client
from app.db.models import Assessment, Candidate
from app.interview.service import GuideError, build_guide


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.interview")
    parser.add_argument("--candidate-code", required=True)
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
        assessment_id = session.scalar(
            select(Assessment.id).join(Candidate, Candidate.id == Assessment.candidate_id)
            .where(Candidate.code == args.candidate_code, Assessment.is_current)
            .order_by(Assessment.created_at.desc())
        )
        if assessment_id is None:
            print(json.dumps({"status": "assessment_required", "error": "у кандидата нет текущей оценки"},
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
