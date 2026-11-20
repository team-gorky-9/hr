"""Учебный корпус для повторяемого CLI/HTTP-прогона."""
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import ApplicationSource, Channel, DocumentKind, FileFormat
from app.db.models import Candidate, Position, Vacancy
from app.db.seed import seed_all
from app.schemas.card import CandidateCard, Education, Skill
from app.search.evaluation import DEFAULT_FIXTURE


def load_demo(session: Session) -> dict[str, int]:
    corpus = json.loads(DEFAULT_FIXTURE.read_bytes())
    created = reused = 0
    seed_all(session)
    for row in corpus["documents"]:
        code = row["code"]
        candidate = session.scalar(select(Candidate).where(Candidate.code == code))
        if candidate is not None:
            current = repo.get_current_text(session, candidate.id)
            if not candidate.is_synthetic or not current or current.text != row["text"]:
                raise ValueError("Код учебной записи занят кандидатом с другим очищенным текстом")
            reused += 1
            continue
        source, _ = repo.add_source_document(
            session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.HH_TXT,
            original_path=f"Учебный поиск/{code}.txt", raw_text=row["text"],
            content=(code + "\n" + row["text"]).encode("utf-8"), import_batch=corpus["version"],
        )
        candidate = repo.create_candidate(
            session, code=code, source_document_id=source.id, redacted_text=row["text"],
            redaction_method=corpus["version"], is_synthetic=True,
        )
        education = [Education(level=row["education_level"])] if row["education_level"] else []
        repo.add_candidate_card(
            session, candidate.id, CandidateCard(education=education, skills=[Skill(name=skill) for skill in row["skills"]]),
            extractor=corpus["version"],
        )
        if row["in_reserve"]:
            repo.add_to_reserve(session, candidate_id=candidate.id, competency_area="учебный пример поиска")
        if code == "search-9001":
            _examples_of_applications(session, candidate)
        created += 1
    return {"created": created, "reused": reused}


def _examples_of_applications(session: Session, candidate: Candidate) -> None:
    for code, source, publication in (
        ("hr-consultant", ApplicationSource.RESPONSE, "Аналитик требований · архивная публикация"),
        ("python-dev", ApplicationSource.MANUAL, None),
    ):
        vacancy_id = session.scalar(
            select(Vacancy.id).join(Position).where(Position.code == code).order_by(Vacancy.id).limit(1)
        )
        if vacancy_id is None:
            raise ValueError("Не найдена должность для учебного отклика")
        repo.create_application(
            session, candidate_id=candidate.id, source=source, vacancy_id=vacancy_id,
            posting_title=publication, applied_at=date(2026, 11, 19),
        )
    repo.create_application(
        session, candidate_id=candidate.id, source=ApplicationSource.HISTORY,
        external_position_title="Специалист по архиву · старая публикация", applied_at=date(2026, 8, 1),
    )
