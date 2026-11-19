import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import repository as repo
from app.db.enums import AuditAction, Channel, DocumentKind, FileFormat
from app.db.models import AuditLog, CandidatePii, CandidateSkill
from app.schemas.card import CandidateCard
from app.schemas.pii import PiiData
from tests.factories import add_card, make_candidate


def test_same_file_is_not_imported_twice(session):
    kwargs = dict(
        kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.HH_TXT,
        original_path="Python-разработчик/отклик 5.txt", raw_text="текст", content=b"bytes",
    )
    first, created_first = repo.add_source_document(session, **kwargs)
    second, created_second = repo.add_source_document(session, **kwargs)
    assert (created_first, created_second) == (True, False)
    assert first.id == second.id
    assert first.file_name == "отклик 5.txt"


def test_nfd_path_is_normalized(session):
    nfd = "Junior UX_UI Дизайнер/отклик 1.txt"  # «й» как «и» + знак, как в архиве
    document, _ = repo.add_source_document(
        session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.HH_TXT,
        original_path=nfd, raw_text="x",
    )
    assert document.original_path == "Junior UX_UI Дизайнер/отклик 1.txt"


def test_candidate_keeps_pii_separately(session):
    document, _ = repo.add_source_document(
        session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.HH_DOCX,
        original_path="консультант/Резюме 10.docx", raw_text="ФИО 10, Мужчина, 28 лет …",
    )
    candidate = repo.create_candidate(
        session, code="hr-0010", source_document=document,
        redacted_text="[скрыто] Опыт работы — 5 лет 9 месяцев", redaction_method="test",
        pii=PiiData(full_name="ФИО 10", gender="Мужчина", age=28),
    )
    assert repo.get_current_text(session, candidate.id).text.startswith("[скрыто]")
    pii = session.get(CandidatePii, candidate.id)
    assert (pii.full_name, pii.age) == ("ФИО 10", 28)


def test_resume_only_documents_become_candidates(session):
    document, _ = repo.add_source_document(
        session, kind=DocumentKind.JOB_DESCRIPTION, channel=Channel.INTERNAL, file_format=FileFormat.DOCX,
        original_path="ДИ.docx", raw_text="ДОЛЖНОСТНАЯ ИНСТРУКЦИЯ",
    )
    with pytest.raises(repo.RepositoryError):
        repo.create_candidate(session, code="x-1", source_document=document, redacted_text="", redaction_method="t")


def test_candidate_code_is_unique(session):
    make_candidate(session, "py-0001")
    with pytest.raises(IntegrityError):
        make_candidate(session, "py-0001", text="другой текст, другой файл")


def test_card_versions_keep_history_and_switch_skills(session):
    candidate = make_candidate(session, "py-0002")
    first = add_card(session, candidate, ["Python", "Flask"])
    second = add_card(session, candidate, ["Python", "FastAPI"], missing=["сопроводительное письмо"])

    session.refresh(first)
    assert (first.version, first.is_current) == (1, False)
    assert (second.version, second.is_current, second.missing_count) == (2, True, 1)
    assert repo.get_current_card(session, candidate.id).id == second.id
    # Поиск по навыкам смотрит только текущую версию карточки.
    assert repo.find_candidates_by_skills(session, ["flask"]) == []
    assert repo.find_candidates_by_skills(session, ["fastapi"]) == [candidate]


def test_card_without_text_is_rejected(session):
    candidate = make_candidate(session, "py-0003")
    other = make_candidate(session, "py-0004", text="Другой кандидат")
    with pytest.raises(repo.RepositoryError):
        repo.add_candidate_card(
            session, candidate, CandidateCard(), extractor="t",
            candidate_text=repo.get_current_text(session, other.id),
        )


def test_skills_are_normalized_and_deduplicated(session):
    candidate = make_candidate(session, "py-0005")
    card = add_card(session, candidate, ["  PostgreSQL ", "postgresql", "Работа с ёмкими данными"])
    names = sorted(s.normalized for s in session.scalars(select(CandidateSkill).where(CandidateSkill.card_id == card.id)))
    assert names == ["postgresql", "работа с емкими данными"]


def test_find_by_skills_all_or_any(session):
    a = make_candidate(session, "py-0010")
    b = make_candidate(session, "py-0011", text="Другой")
    add_card(session, a, ["Python", "Docker"])
    add_card(session, b, ["Python"])
    assert repo.find_candidates_by_skills(session, ["python", "docker"]) == [a]
    assert repo.find_candidates_by_skills(session, ["Docker", "Kafka"], match_all=False) == [a]
    assert repo.find_candidates_by_skills(session, ["python"]) == [a, b]
    assert repo.find_candidates_by_skills(session, ["  "]) == []


def test_reading_pii_is_audited(session):
    candidate = make_candidate(session, "py-0020")
    repo.get_candidate_pii(session, candidate.id, user_id=None, purpose="звонок кандидату")
    entry = session.scalar(select(AuditLog).where(AuditLog.entity_id == str(candidate.id)))
    assert entry.action == AuditAction.VIEW_PII
    assert entry.details == {"purpose": "звонок кандидату"}
