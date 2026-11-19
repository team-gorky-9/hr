"""Сборка тестовых данных. Тексты здесь синтетические и короткие —
проверка на реальном резюме сделана отдельным скриптом scripts/smoke_real_candidate.py."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import repository as repo
from app.db.enums import Channel, CompetencyRank, DocumentKind, FileFormat, FormalRequirementKind
from app.db.models import Candidate, Competency, FormalRequirement, Position, RequirementProfile, Vacancy
from app.schemas.card import CandidateCard, Skill


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
        session, code=code, source_document=document, redacted_text=text, redaction_method="test"
    )


def add_card(session: Session, candidate: Candidate, skills: list[str], **fields):
    card = CandidateCard(skills=[Skill(name=s) for s in skills], **fields)
    return repo.add_candidate_card(session, candidate, card, extractor="test")


def position(session: Session, code: str = "python-dev") -> Position:
    return session.scalar(select(Position).where(Position.code == code))


def vacancy(session: Session, code: str = "python-dev") -> Vacancy:
    return session.scalar(select(Vacancy).join(Position).where(Position.code == code))


def make_profile(session: Session, position_code: str = "hr-consultant", version: int = 1) -> RequirementProfile:
    """Профиль по мотивам ДИ и матрицы консультанта (сокращённо)."""
    profile = RequirementProfile(
        position_id=position(session, position_code).id, version=version, created_by="test"
    )
    profile.formal_requirements = [
        FormalRequirement(
            kind=FormalRequirementKind.EDUCATION_LEVEL,
            description="Высшее образование",
            params={"min_level": "высшее"},
            sort_order=1,
        ),
        FormalRequirement(
            kind=FormalRequirementKind.EDUCATION_FIELD,
            description="Юриспруденция или ГМУ либо переподготовка",
            is_mandatory=False,
            sort_order=2,
        ),
    ]
    profile.competencies = [
        Competency(rank=CompetencyRank.KEY, code="ИТК", name="Информационно-техническая компетенция",
                   target_level_min=90, target_level_max=100, sort_order=1),
    ]
    session.add(profile)
    session.flush()
    return profile
