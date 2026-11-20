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
    UserRole,
    VerificationMethod,
)
from app.db.models import Candidate, Position, RequirementProfile, User, Vacancy
from app.schemas.card import CandidateCard, Skill
from app.schemas.requirements import CompetencyIn, FormalRequirementIn, IndicatorIn


def make_candidate(
    session: Session, code: str, text: str = "Опыт: Python, FastAPI. Писал тесты на Pytest.", is_synthetic: bool = False
) -> Candidate:
    document, _ = repo.add_source_document(
        session,
        kind=DocumentKind.RESUME,
        channel=Channel.HH_RU,
        file_format=FileFormat.HH_TXT,
        original_path=f"Тест/{code}.txt",
        raw_text=f"{code}\n{text}",
    )
    return repo.create_candidate(
        session, code=code, source_document_id=document.id, redacted_text=text, redaction_method="test",
        is_synthetic=is_synthetic,
    )


def add_card(session: Session, candidate: Candidate, skills: list[str], **fields):
    card = CandidateCard(skills=[Skill(name=s) for s in skills], **fields)
    return repo.add_candidate_card(session, candidate.id, card, extractor="test")


def position(session: Session, code: str = "python-dev") -> Position:
    return session.scalar(select(Position).where(Position.code == code))


def vacancy(session: Session, code: str = "python-dev") -> Vacancy:
    return session.scalar(select(Vacancy).join(Position).where(Position.code == code))


EDUCATION_LEVEL_PARAMS = {"schema_version": "0.1", "alternatives": [{"key": "t.education.level.alt1", "level": "высшее"}]}
EDUCATION_FIELD_PARAMS = {
    "schema_version": "0.1",
    "alternatives": [
        {"key": "t.education.field.alt1", "degree_fields": ["Юриспруденция", "Государственное и муниципальное управление"]},
        {"key": "t.education.field.alt2", "retraining_fields": ["Юриспруденция", "Государственное и муниципальное управление"]},
    ],
    "requires_requirement": "t.education.level",
}


def make_user(session: Session, role: UserRole = UserRole.HR, login: str = "hr-1", active: bool = True) -> User:
    row = User(login=login, full_name="Кадровик", role=role, is_active=active)
    session.add(row)
    session.flush()
    return row


def approve(session: Session, profile: RequirementProfile, approver: User | None = None) -> RequirementProfile:
    """Утвердить профиль от имени кадровика (заводится, если не передан)."""
    approver = approver or session.scalar(select(User).where(User.login == "hr-approver")) or make_user(
        session, login="hr-approver"
    )
    return repo.approve_requirement_profile(
        session, profile.id, approved_by_user_id=approver.id, approval_basis="тестовое утверждение"
    )


def make_profile(
    session: Session, position_code: str = "hr-consultant", version: int | None = 1, is_synthetic: bool = False
) -> RequirementProfile:
    """Профиль по мотивам ДИ и матрицы консультанта (сокращённо). Строки без документа:
    помечены как строки команды, чтобы тесты не зависели от загрузки ДИ."""
    team = {"origin": RowOrigin.TEAM, "note": "тестовые данные"}
    return repo.create_requirement_profile(
        session,
        position_id=position(session, position_code).id,
        version=version,
        is_synthetic=is_synthetic,
        created_by="test",
        formal_requirements=[
            FormalRequirementIn(kind=FormalRequirementKind.EDUCATION_LEVEL, key="t.education.level", description="Высшее образование",
                                params=EDUCATION_LEVEL_PARAMS, verification=VerificationMethod.RESUME, **team),
            FormalRequirementIn(kind=FormalRequirementKind.EDUCATION_FIELD, key="t.education.field",
                                description="Юриспруденция или ГМУ либо переподготовка", is_mandatory=False,
                                params=EDUCATION_FIELD_PARAMS,
                                verification=VerificationMethod.DOCUMENTS, **team),
        ],
        competencies=[
            CompetencyIn(key="t.ITK", rank=CompetencyRank.KEY, code="ИТК", name="Информационно-техническая компетенция",
                         target_level_min=90, target_level_max=100, **team,
                         indicators=[IndicatorIn(key="t.ITK.01", text="умеет работать с базами данных",
                                                 verification=VerificationMethod.RESUME, **team)]),
        ],
    )
