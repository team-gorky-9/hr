"""Сборка тестовых данных. Тексты здесь синтетические и короткие —
проверка на реальном резюме сделана отдельным скриптом scripts/smoke_real_candidate.py."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import (
    Channel,
    CompetencyRank,
    DocumentKind,
    FileFormat,
    FormalRequirementKind,
    RowOrigin,
    VerificationMethod,
)
from app.db.models import Candidate, Position, RequirementProfile, Vacancy
from app.schemas.card import CandidateCard, Skill
from app.schemas.requirements import CompetencyIn, FormalRequirementIn, IndicatorIn


def make_candidate(session: Session, code: str, text: str = "Опыт: Python, FastAPI. Писал тесты на Pytest.") -> Candidate:
    document, _ = repo.add_source_document(
        session,
        kind=DocumentKind.RESUME,
        channel=Channel.HH_RU,
        file_format=FileFormat.HH_TXT,
        original_path=f"Тест/{code}.txt",
        raw_text=f"{code}\n{text}",
    )
    return repo.create_candidate(
        session, code=code, source_document_id=document.id, redacted_text=text, redaction_method="test"
    )


def add_card(session: Session, candidate: Candidate, skills: list[str], **fields):
    card = CandidateCard(skills=[Skill(name=s) for s in skills], **fields)
    return repo.add_candidate_card(session, candidate.id, card, extractor="test")


def position(session: Session, code: str = "python-dev") -> Position:
    return session.scalar(select(Position).where(Position.code == code))


def vacancy(session: Session, code: str = "python-dev") -> Vacancy:
    return session.scalar(select(Vacancy).join(Position).where(Position.code == code))


def make_profile(session: Session, position_code: str = "hr-consultant", version: int = 1) -> RequirementProfile:
    """Профиль по мотивам ДИ и матрицы консультанта (сокращённо). Строки без документа:
    помечены как строки команды, чтобы тесты не зависели от загрузки ДИ."""
    team = {"origin": RowOrigin.TEAM, "note": "тестовые данные"}
    return repo.create_requirement_profile(
        session,
        position_id=position(session, position_code).id,
        version=version,
        created_by="test",
        formal_requirements=[
            FormalRequirementIn(kind=FormalRequirementKind.EDUCATION_LEVEL, description="Высшее образование",
                                params={"min_level": "высшее"}, verification=VerificationMethod.RESUME, **team),
            FormalRequirementIn(kind=FormalRequirementKind.EDUCATION_FIELD,
                                description="Юриспруденция или ГМУ либо переподготовка", is_mandatory=False,
                                verification=VerificationMethod.DOCUMENTS, **team),
        ],
        competencies=[
            CompetencyIn(rank=CompetencyRank.KEY, code="ИТК", name="Информационно-техническая компетенция",
                         target_level_min=90, target_level_max=100, **team,
                         indicators=[IndicatorIn(text="умеет работать с базами данных",
                                                 verification=VerificationMethod.RESUME, **team)]),
        ],
    )
