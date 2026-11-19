"""Профили требований в едином формате: создание, происхождение строк, утверждение.

Цитаты взяты из документов архива «Кадры» (ДИ консультанта сектора, матрица
консультанта, ДИ и вакансия Python-разработчика); сами документы в тесте короткие.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import repository as repo
from app.db.enums import (
    Channel,
    CompetencyRank,
    DocumentKind,
    FileFormat,
    FormalRequirementKind,
    RequirementStatus,
    RowOrigin,
    SourceRole,
    UserRole,
    VerificationMethod,
)
from app.db.models import User
from app.schemas.requirements import CompetencyIn, FormalRequirementIn, IndicatorIn, ProfileSourceIn
from tests.factories import add_card, make_candidate, make_profile, position

HR_EDUCATION = (
    "Консультант должен иметь высшее образование по специальности, направлению подготовки «Юриспруденция», "
    "«Государственное и муниципальное управление»"
)
ITK_INDICATOR = "умеет работать с информационными ресурсами, в т.ч. с базами данных, интернет-сайтами"
PY_EDUCATION = "высшее техническое образование (или студент ВУЗа старших курсов)"
PY_PUNCTUAL = "пунктуальность"
PY_CLICKHOUSE = "Навыки работы с ClickHouse будут преимуществом"
TEAM = {"origin": RowOrigin.TEAM, "note": "группировка команды по разделу 2 ДИ"}


def document(session, kind: DocumentKind, path: str, raw_text: str):
    doc, _ = repo.add_source_document(
        session, kind=kind, channel=Channel.INTERNAL, file_format=FileFormat.DOCX,
        original_path=path, raw_text=raw_text,
    )
    return doc


def quoted(doc, ref: str, quote: str) -> dict:
    return {"origin": RowOrigin.SOURCE, "source_document_id": doc.id, "source_ref": ref, "source_quote": quote}


def user(session, role: UserRole = UserRole.HR, login: str = "hr-1", active: bool = True) -> User:
    row = User(login=login, full_name="Кадровик", role=role, is_active=active)
    session.add(row)
    session.flush()
    return row


def consultant_profile(session, **kwargs):
    di = document(session, DocumentKind.JOB_DESCRIPTION, "Положения/ДИ консультант.docx", HR_EDUCATION)
    matrix = document(session, DocumentKind.COMPETENCY_MATRIX, "матрица.docx", "ИТК 90-100 процентов " + ITK_INDICATOR)
    profile = repo.create_requirement_profile(
        session,
        position_id=position(session, "hr-consultant").id,
        created_by="david",
        sources=[
            ProfileSourceIn(source_document_id=di.id, role=SourceRole.JOB_DESCRIPTION, is_primary=True),
            ProfileSourceIn(source_document_id=matrix.id, role=SourceRole.COMPETENCY_MATRIX),
        ],
        formal_requirements=[
            FormalRequirementIn(kind=FormalRequirementKind.EDUCATION_FIELD, description="Юриспруденция или ГМУ",
                                verification=VerificationMethod.DOCUMENTS, **quoted(di, "п. 2.2.1", HR_EDUCATION)),
        ],
        competencies=[
            CompetencyIn(rank=CompetencyRank.KEY, code="ИТК", name="Информационно-техническая компетенция",
                         target_level_min=90, target_level_max=100, **quoted(matrix, "ИТК", "90-100 процентов"),
                         indicators=[IndicatorIn(text=ITK_INDICATOR, verification=VerificationMethod.RESUME,
                                                 **quoted(matrix, "ИТК, инд. 2", ITK_INDICATOR))]),
        ],
        **kwargs,
    )
    return profile, di, matrix


def python_profile(session):
    di = document(session, DocumentKind.JOB_DESCRIPTION, "Python-разработчик/ДИ.docx",
                  PY_EDUCATION + "\n" + PY_PUNCTUAL)
    posting = document(session, DocumentKind.VACANCY_POSTING, "Python-разработчик/Вакансия.txt", PY_CLICKHOUSE)
    return repo.create_requirement_profile(
        session,
        position_id=position(session, "python-dev").id,
        created_by="david",
        sources=[
            ProfileSourceIn(source_document_id=di.id, role=SourceRole.JOB_DESCRIPTION,
                            observed_revision="1.2 от 01.02.2024", is_primary=True),
            ProfileSourceIn(source_document_id=posting.id, role=SourceRole.VACANCY_POSTING),
        ],
        formal_requirements=[
            FormalRequirementIn(kind=FormalRequirementKind.EDUCATION_LEVEL, description=PY_EDUCATION,
                                params={"alternatives": [{"level": "высшее", "field_group": "техническое"},
                                                         {"enrollment_status": "старшие курсы"}]},
                                verification=VerificationMethod.RESUME,
                                **quoted(di, "разд. 7, стр. 1", PY_EDUCATION)),
        ],
        competencies=[
            CompetencyIn(code="PY-DB", name="Базы данных", **TEAM, indicators=[
                IndicatorIn(text="Навыки работы с ClickHouse", is_mandatory=False,
                            verification=VerificationMethod.RESUME,
                            **quoted(posting, "Требования, стр. 5", PY_CLICKHOUSE)),
            ]),
            CompetencyIn(code="PY-PERSONAL", name="Личные качества", **TEAM, indicators=[
                IndicatorIn(text="Пунктуальность", verification=VerificationMethod.INTERVIEW,
                            **quoted(di, "разд. 7, стр. 4", PY_PUNCTUAL)),
            ]),
        ],
    )


# --- Создание ----------------------------------------------------------------

def test_profile_with_matrix_keeps_rank_and_target(session):
    profile, di, matrix = consultant_profile(session)

    assert profile.status == RequirementStatus.DRAFT and profile.version == 1
    assert {s.source_document_id for s in profile.sources} == {di.id, matrix.id}
    itk = profile.competencies[0]
    assert (itk.rank, itk.target_level_min, itk.target_level_max) == (CompetencyRank.KEY, 90, 100)
    indicator = itk.indicators[0]
    assert indicator.is_mandatory and indicator.verification == VerificationMethod.RESUME
    assert (indicator.source_ref, indicator.source_quote) == ("ИТК, инд. 2", ITK_INDICATOR)


def test_profile_without_matrix_has_no_rank_and_target(session):
    profile = python_profile(session)

    assert [c.code for c in profile.competencies] == ["PY-DB", "PY-PERSONAL"]
    assert [c.sort_order for c in profile.competencies] == [1, 2]
    for competency in profile.competencies:
        assert competency.rank is None and competency.target_level_min is None and competency.target_level_max is None
        assert competency.origin == RowOrigin.TEAM
    clickhouse = profile.competencies[0].indicators[0]
    assert not clickhouse.is_mandatory  # «будет преимуществом»
    assert profile.competencies[1].indicators[0].verification == VerificationMethod.INTERVIEW
    assert profile.sources[0].observed_revision == "1.2 от 01.02.2024"


def test_next_version_is_assigned_and_repeat_is_rejected(session):
    make_profile(session, "python-dev", version=1)
    second = repo.create_requirement_profile(
        session, position_id=position(session, "python-dev").id, created_by="test",
        formal_requirements=[], competencies=[],
    )
    assert second.version == 2
    with pytest.raises(IntegrityError):
        make_profile(session, "python-dev", version=2)


def test_row_document_must_be_among_profile_sources(session):
    stray = document(session, DocumentKind.JOB_DESCRIPTION, "Другое/ДИ.docx", HR_EDUCATION)
    with pytest.raises(repo.RepositoryError, match="нет в источниках профиля"):
        repo.create_requirement_profile(
            session, position_id=position(session).id, created_by="test", competencies=[],
            formal_requirements=[FormalRequirementIn(
                kind=FormalRequirementKind.EDUCATION_FIELD, description="ГМУ",
                verification=VerificationMethod.DOCUMENTS, **quoted(stray, "п. 2.2.1", HR_EDUCATION))],
        )


def test_duplicate_competency_codes_are_rejected(session):
    competency = CompetencyIn(code="ИТК", name="ИТК", **TEAM, indicators=[
        IndicatorIn(text="умеет", verification=VerificationMethod.RESUME, **TEAM)])
    with pytest.raises(repo.RepositoryError, match="повторяются коды"):
        repo.create_requirement_profile(session, position_id=position(session).id, created_by="test",
                                        formal_requirements=[], competencies=[competency, competency])


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"origin": RowOrigin.SOURCE, "source_ref": "п. 2.1.1"}, "source_document_id, source_quote"),
        ({"origin": RowOrigin.TEAM}, "обоснование"),
    ],
)
def test_row_origin_rules(fields, message):
    with pytest.raises(ValidationError, match=message):
        IndicatorIn(text="умеет", verification=VerificationMethod.RESUME, **fields)


def test_target_level_is_both_or_none():
    with pytest.raises(ValidationError, match="двумя числами"):
        CompetencyIn(code="X", name="X", target_level_min=90, **TEAM,
                     indicators=[IndicatorIn(text="умеет", verification=VerificationMethod.RESUME, **TEAM)])


def test_database_rejects_source_row_without_quote(session):
    """Правило происхождения держит и сама база, а не только функция доступа."""
    profile = make_profile(session)
    with pytest.raises(IntegrityError, match="ck_competency_indicators_row_source"):
        session.execute(
            text("INSERT INTO competency_indicators (competency_id, text, verification, origin)"
                 " VALUES (:c, 'умеет', 'resume', 'source')"),
            {"c": profile.competencies[0].id},
        )


# --- Утверждение -------------------------------------------------------------

def test_approve_archives_previous_version(session):
    first, _, _ = consultant_profile(session)
    approver = user(session)
    repo.approve_requirement_profile(session, first.id, approved_by_user_id=approver.id,
                                     approval_basis="согласовано с начальником отдела")
    second = make_profile(session, "hr-consultant", version=2)

    approved = repo.approve_requirement_profile(session, second.id, approved_by_user_id=approver.id,
                                                approval_basis="  распоряжение № 1  ")

    session.refresh(first)
    assert first.status == RequirementStatus.ARCHIVED
    assert approved.status == RequirementStatus.APPROVED
    assert approved.approved_by_user_id == approver.id and approved.approved_at is not None
    assert approved.approval_basis == "распоряжение № 1"


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("synthetic", "учебный профиль"),
        ("department", "кадровик или администратор"),
        ("inactive", "кадровик или администратор"),
        ("no_basis", "основание"),
        ("twice", "только черновик"),
    ],
)
def test_approve_rules(session, setup, message):
    profile, _, _ = consultant_profile(session, is_synthetic=setup == "synthetic")
    role = UserRole.DEPARTMENT if setup == "department" else UserRole.HR
    approver = user(session, role=role, active=setup != "inactive")
    basis = "" if setup == "no_basis" else "распоряжение № 1"
    if setup == "twice":
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=approver.id, approval_basis=basis)
    with pytest.raises(repo.RepositoryError, match=message):
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=approver.id, approval_basis=basis)


def test_assessment_by_archived_profile_is_rejected(session):
    first = make_profile(session)
    approver = user(session)
    repo.approve_requirement_profile(session, first.id, approved_by_user_id=approver.id, approval_basis="№ 1")
    second = make_profile(session, version=2)
    repo.approve_requirement_profile(session, second.id, approved_by_user_id=approver.id, approval_basis="№ 2")
    candidate = make_candidate(session, "hr-0300")
    card = add_card(session, candidate, ["Базы данных"])

    with pytest.raises(repo.RepositoryError, match="в архиве"):
        repo.save_assessment(session, candidate_id=candidate.id, profile_id=first.id, card_id=card.id,
                             model="test", formal_checks=[], competency_scores=[])
