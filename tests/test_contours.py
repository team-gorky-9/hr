"""Учебный и рабочий контуры, основание результата, альтернативы, этап проверки (контракт БД v1.5).

Главный риск, который проверяют тесты: учебный профиль (выдуманное правило «стаж ≥ 24 мес.»)
не должен архивировать рабочий профиль и не должен стать основой рабочей оценки реального
человека — ни через утверждение, ни через выбор действующего профиля, ни через запись оценки.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import repository as repo
from app.db.enums import (
    CheckResult,
    CheckStage,
    FormalRequirementKind,
    RequirementStatus,
    RowOrigin,
    UserRole,
    VerificationMethod,
)
from app.schemas.assessment import AlternativeResultIn, FormalCheckIn
from app.schemas.card import Evidence
from app.schemas.requirements import CompetencyIn, FormalRequirementIn, IndicatorIn
from tests.factories import add_card, approve, make_candidate, make_profile, make_user, position

TEAM = {"origin": RowOrigin.TEAM, "note": "тестовые данные"}
TEXT = "Высшее образование, Юриспруденция, 2015. Работал с базами данных."


def quote(text_row, fragment: str) -> Evidence:
    start = text_row.text.index(fragment)
    return Evidence(candidate_text_id=text_row.id, quote=fragment, start=start, end=start + len(fragment))


def save(session, candidate, profile, card, checks=()):
    return repo.save_assessment(session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id,
                                model="test", formal_checks=list(checks), competency_scores=[])


# --- Утверждение и нумерация по контуру ----------------------------------------

def test_approving_training_profile_keeps_working_profile_approved(session):
    working = approve(session, make_profile(session, "python-dev", version=1))
    training = approve(session, make_profile(session, "python-dev", version=1, is_synthetic=True))

    session.refresh(working)
    assert (working.status, training.status) == (RequirementStatus.APPROVED, RequirementStatus.APPROVED)


def test_approving_working_profile_keeps_training_profile_approved(session):
    training = approve(session, make_profile(session, "python-dev", version=1, is_synthetic=True))
    approve(session, make_profile(session, "python-dev", version=1))

    session.refresh(training)
    assert training.status == RequirementStatus.APPROVED


def test_new_training_version_archives_only_previous_training_version(session):
    working = approve(session, make_profile(session, "python-dev", version=1))
    old_training = approve(session, make_profile(session, "python-dev", version=1, is_synthetic=True))
    approve(session, make_profile(session, "python-dev", version=2, is_synthetic=True))

    session.refresh(working)
    session.refresh(old_training)
    assert old_training.status == RequirementStatus.ARCHIVED
    assert working.status == RequirementStatus.APPROVED


def test_database_allows_one_approved_profile_per_position_and_contour(session):
    """Индекс держит правило и без функции утверждения: два утверждённых в одном контуре — ошибка."""
    first = make_profile(session, "python-dev", version=1, is_synthetic=True)
    second = make_profile(session, "python-dev", version=2, is_synthetic=True)
    first.status = RequirementStatus.APPROVED
    session.flush()
    second.status = RequirementStatus.APPROVED
    with pytest.raises(IntegrityError, match="uq_requirement_profiles_approved"):
        session.flush()


def test_versions_are_numbered_per_contour(session):
    """Учебный python-dev v2 из synthetic/cases.json сосуществует с рабочим v2 из profiles.draft.json."""
    make_profile(session, "python-dev", version=2)
    training = make_profile(session, "python-dev", version=2, is_synthetic=True)
    assert training.version == 2

    next_training = make_profile(session, "python-dev", version=None, is_synthetic=True)
    next_working = make_profile(session, "python-dev", version=None)
    assert (next_training.version, next_working.version) == (3, 3)
    with pytest.raises(IntegrityError):
        make_profile(session, "python-dev", version=2, is_synthetic=True)


def test_training_profile_is_approved_by_the_same_rules(session):
    profile = make_profile(session, "python-dev", is_synthetic=True)
    department = make_user(session, role=UserRole.DEPARTMENT, login="dep-1")
    with pytest.raises(repo.RepositoryError, match="кадровик или администратор"):
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=department.id,
                                         approval_basis="учебный набор")
    hr = make_user(session, login="hr-2")
    with pytest.raises(repo.RepositoryError, match="основание"):
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=hr.id, approval_basis=" ")


# --- Выбор действующего профиля ------------------------------------------------

def test_get_approved_profile_returns_working_profile_by_default(session):
    python_dev = position(session, "python-dev").id
    training = approve(session, make_profile(session, "python-dev", is_synthetic=True))

    assert repo.get_approved_profile(session, python_dev) is None
    assert repo.get_approved_profile(session, python_dev, synthetic=True).id == training.id

    working = approve(session, make_profile(session, "python-dev"))
    assert repo.get_approved_profile(session, python_dev).id == working.id
    assert repo.get_approved_profile(session, python_dev, synthetic=True).id == training.id


def test_draft_is_not_selected(session):
    make_profile(session, "python-dev")
    assert repo.get_approved_profile(session, position(session, "python-dev").id) is None


# --- Кого по какому профилю можно оценить --------------------------------------

def test_real_candidate_is_not_assessed_by_approved_training_profile(session):
    candidate = make_candidate(session, "py-0400")
    card = add_card(session, candidate, ["Python"])
    training = approve(session, make_profile(session, "python-dev", is_synthetic=True))
    with pytest.raises(repo.RepositoryError, match="учебному профилю"):
        save(session, candidate, training, card)


def test_real_candidate_is_not_assessed_by_draft(session):
    candidate = make_candidate(session, "py-0401")
    card = add_card(session, candidate, ["Python"])
    draft = make_profile(session, "python-dev")
    with pytest.raises(repo.RepositoryError, match="только по утверждённому"):
        save(session, candidate, draft, card)


def test_real_candidate_is_assessed_by_approved_working_profile(session):
    candidate = make_candidate(session, "py-0402")
    card = add_card(session, candidate, ["Python"])
    working = approve(session, make_profile(session, "python-dev"))
    assessment = save(session, candidate, working, card)
    assert not repo.is_training_assessment(candidate, working)
    assert assessment.is_current


@pytest.mark.parametrize(("profile_synthetic", "approved"), [(True, False), (True, True), (False, False), (False, True)])
def test_training_candidate_is_assessed_by_any_active_profile(session, profile_synthetic, approved):
    """Учебные случаи проверяют и правила реальных профилей (25 случаев stage-0b-01)."""
    candidate = make_candidate(session, "py-9001", is_synthetic=True)
    card = add_card(session, candidate, ["Python"])
    profile = make_profile(session, "python-dev", is_synthetic=profile_synthetic)
    if approved:
        approve(session, profile)
    assessment = save(session, candidate, profile, card)
    assert repo.is_training_assessment(candidate, profile)
    assert assessment.is_current


def test_training_candidate_is_not_assessed_by_archived_profile(session):
    candidate = make_candidate(session, "py-9002", is_synthetic=True)
    card = add_card(session, candidate, ["Python"])
    old = approve(session, make_profile(session, "python-dev", version=1, is_synthetic=True))
    approve(session, make_profile(session, "python-dev", version=2, is_synthetic=True))
    with pytest.raises(repo.RepositoryError, match="в архиве"):
        save(session, candidate, old, card)


# --- Признак контура не меняется ------------------------------------------------

@pytest.mark.parametrize("table", ["requirement_profiles", "candidates"])
def test_database_rejects_contour_change(session, table):
    row = make_profile(session, "python-dev") if table == "requirement_profiles" else make_candidate(session, "py-0403")
    with pytest.raises(DBAPIError, match="is_synthetic"):
        with session.begin_nested():
            session.execute(text(f"UPDATE {table} SET is_synthetic = true WHERE id = :id"), {"id": row.id})


# --- Основание результата и подтверждение человеком ------------------------------

def setup_documents_requirement(session):
    """Реальный кандидат, утверждённый профиль с обязательным направлением «по документам»."""
    candidate = make_candidate(session, "hr-0500", text=TEXT)
    card = add_card(session, candidate, ["Базы данных"])
    profile = make_profile(session)
    level_req, field_req = profile.formal_requirements
    field_req.is_mandatory = True
    session.flush()
    approve(session, profile)
    text_row = repo.get_current_text(session, candidate.id)
    first = save(session, candidate, profile, card, [
        FormalCheckIn(requirement_id=level_req.id, result=CheckResult.MET, evidence=[quote(text_row, "Высшее образование")]),
        FormalCheckIn(requirement_id=field_req.id, result=CheckResult.MET, evidence=[quote(text_row, "Юриспруденция")]),
    ])
    return candidate, profile, field_req, first


def test_document_confirmation_creates_new_version_and_keeps_history(session):
    candidate, profile, field_req, first = setup_documents_requirement(session)
    hr = make_user(session, login="hr-docs")

    second = repo.confirm_formal_check(
        session, assessment_id=first.id, requirement_id=field_req.id, result=CheckResult.MET,
        basis=VerificationMethod.DOCUMENTS, actor_user_id=hr.id, comment="диплом проверен",
    )

    session.refresh(first)
    assert (first.is_current, second.is_current, second.version) == (False, True, 2)
    old = next(c for c in first.formal_checks if c.requirement_id == field_req.id)
    new = next(c for c in second.formal_checks if c.requirement_id == field_req.id)
    assert (old.basis, old.evidence != [], old.is_preliminary) == (VerificationMethod.RESUME, True, True)
    assert (new.basis, new.confirmed_by_user_id, new.evidence) == (VerificationMethod.DOCUMENTS, hr.id, [])
    assert not new.is_preliminary
    # Уровень образования (verification = resume) не предварительный: после диплома допуск окончательный.
    assert (first.formal_preliminary, second.formal_preliminary) == (True, False)
    # Остальные строки перенесены как были.
    assert len(second.formal_checks) == len(first.formal_checks)
    assert second.formal_result == CheckResult.MET


def test_not_met_by_resume_on_documents_requirement_is_preliminary_too(session):
    """По контракту оценки п. 4.4 предварительность не зависит от знака вывода: «по резюме нет» тоже
    сверяется с документом. Итог допуска при этом not_met, а formal_preliminary относится только к met."""
    candidate = make_candidate(session, "hr-0501", text="Среднее профессиональное образование, 2015.")
    card = add_card(session, candidate, ["Базы данных"])
    profile = make_profile(session)
    field_req = profile.formal_requirements[1]
    field_req.is_mandatory = True
    session.flush()
    approve(session, profile)
    assessment = save(session, candidate, profile, card,
                      [FormalCheckIn(requirement_id=field_req.id, result=CheckResult.NOT_MET)])
    check = assessment.formal_checks[0]
    assert (check.is_preliminary, assessment.formal_result, assessment.formal_preliminary) == (
        True, CheckResult.NOT_MET, False)


def test_document_disproves_preliminary_result(session):
    _, _, field_req, first = setup_documents_requirement(session)
    hr = make_user(session, login="hr-docs")
    second = repo.confirm_formal_check(
        session, assessment_id=first.id, requirement_id=field_req.id, result=CheckResult.NOT_MET,
        basis=VerificationMethod.DOCUMENTS, actor_user_id=hr.id, comment="в дипломе другое направление",
    )
    assert (first.formal_result, second.formal_result) == (CheckResult.MET, CheckResult.NOT_MET)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"basis": VerificationMethod.RESUME}, "save_assessment"),
        ({"comment": "  "}, "основании"),
        ({"role": UserRole.DEPARTMENT}, "кадровик или администратор"),
        ({"old_version": True}, "текущую версию"),
    ],
)
def test_confirmation_rules(session, change, message):
    candidate, profile, field_req, first = setup_documents_requirement(session)
    actor = make_user(session, login="actor", role=change.get("role", UserRole.HR))
    target = first
    if change.get("old_version"):
        repo.confirm_formal_check(session, assessment_id=first.id, requirement_id=field_req.id, result=CheckResult.MET,
                                  basis=VerificationMethod.DOCUMENTS, actor_user_id=actor.id, comment="диплом")
    with pytest.raises(repo.RepositoryError, match=message):
        repo.confirm_formal_check(
            session, assessment_id=target.id, requirement_id=field_req.id, result=CheckResult.MET,
            basis=change.get("basis", VerificationMethod.DOCUMENTS), actor_user_id=actor.id,
            comment=change.get("comment", "диплом проверен"),
        )


def test_database_rejects_resume_quotes_on_human_confirmation(session):
    """Строка «по документу» без подтвердившего или с цитатами резюме — ошибка самой базы."""
    _, _, field_req, first = setup_documents_requirement(session)
    with pytest.raises(IntegrityError, match="ck_formal_checks_basis_confirmation"):
        with session.begin_nested():
            session.execute(text("UPDATE formal_checks SET basis = 'documents' WHERE assessment_id = :a"),
                            {"a": first.id})


# --- Альтернативы ----------------------------------------------------------------

def alternatives_setup(session):
    candidate = make_candidate(session, "hr-0600", text=TEXT)
    card = add_card(session, candidate, ["Базы данных"])
    profile = approve(session, make_profile(session))
    field_req = profile.formal_requirements[1]
    return candidate, card, profile, field_req, repo.get_current_text(session, candidate.id)


def test_alternative_results_are_stored_with_quotes(session):
    candidate, card, profile, field_req, text_row = alternatives_setup(session)
    assessment = save(session, candidate, profile, card, [FormalCheckIn(
        requirement_id=field_req.id, result=CheckResult.MET,
        evidence=[quote(text_row, "Юриспруденция")],
        alternatives=[
            AlternativeResultIn(key="t.education.field.alt1", result=CheckResult.MET,
                                evidence=[quote(text_row, "Юриспруденция")]),
            AlternativeResultIn(key="t.education.field.alt2", result=CheckResult.UNKNOWN),
        ],
    )])
    stored = assessment.formal_checks[0].alternatives
    assert [(a["key"], a["result"]) for a in stored] == [("t.education.field.alt1", "met"), ("t.education.field.alt2", "unknown")]
    assert stored[0]["evidence"][0]["quote"] == "Юриспруденция"


@pytest.mark.parametrize(
    ("result", "alternatives", "message"),
    [
        (CheckResult.MET, [("t.education.field.alt1", CheckResult.MET)], "нужны ровно"),
        (CheckResult.MET, [("t.education.field.alt1", CheckResult.MET), ("t.other", CheckResult.MET)], "нужны ровно"),
        (CheckResult.MET, [("t.education.field.alt1", CheckResult.NOT_MET), ("t.education.field.alt2", CheckResult.NOT_MET)],
         "по альтернативам выходит not_met"),
        (CheckResult.NOT_MET, [("t.education.field.alt1", CheckResult.NOT_MET), ("t.education.field.alt2", CheckResult.UNKNOWN)],
         "по альтернативам выходит unknown"),
    ],
)
def test_alternative_rules(session, result, alternatives, message):
    candidate, card, profile, field_req, _ = alternatives_setup(session)
    check = FormalCheckIn(requirement_id=field_req.id, result=result,
                          alternatives=[AlternativeResultIn(key=k, result=r) for k, r in alternatives])
    with pytest.raises(repo.RepositoryError, match=message):
        save(session, candidate, profile, card, [check])


def test_unknown_is_allowed_with_confirmed_alternative(session):
    """Направление проверяется только при подтверждённом уровне (requires_requirement): если уровень
    unknown, направление unknown, даже когда диплом по направлению найден (альтернатива met)."""
    candidate, card, profile, field_req, text_row = alternatives_setup(session)
    assessment = save(session, candidate, profile, card, [FormalCheckIn(
        requirement_id=field_req.id, result=CheckResult.UNKNOWN,
        alternatives=[AlternativeResultIn(key="t.education.field.alt1", result=CheckResult.MET,
                                          evidence=[quote(text_row, "Юриспруденция")]),
                      AlternativeResultIn(key="t.education.field.alt2", result=CheckResult.UNKNOWN)])])
    assert assessment.formal_checks[0].result == CheckResult.UNKNOWN


def test_alternative_quote_is_verified(session):
    candidate, card, profile, field_req, text_row = alternatives_setup(session)
    fake = Evidence(candidate_text_id=text_row.id, quote="Государственное управление", start=0, end=26)
    with pytest.raises(repo.EvidenceError):
        save(session, candidate, profile, card, [FormalCheckIn(
            requirement_id=field_req.id, result=CheckResult.MET,
            alternatives=[AlternativeResultIn(key="t.education.field.alt1", result=CheckResult.MET, evidence=[fake]),
                          AlternativeResultIn(key="t.education.field.alt2", result=CheckResult.UNKNOWN)])])


def test_alternatives_for_requirement_without_alternatives_are_rejected(session):
    candidate = make_candidate(session, "py-9003", is_synthetic=True)
    card = add_card(session, candidate, ["Python"])
    profile = repo.create_requirement_profile(
        session, position_id=position(session, "python-dev").id, created_by="test", is_synthetic=True,
        competencies=[], formal_requirements=[FormalRequirementIn(
            key="s.experience", kind=FormalRequirementKind.EXPERIENCE, description="стаж ≥ 24 мес.",
            params={"schema_version": "0.1", "scope": "total_commercial", "minimum_defined": True, "min_months": 24},
            verification=VerificationMethod.RESUME, **TEAM)])
    with pytest.raises(repo.RepositoryError, match="нет альтернатив"):
        save(session, candidate, profile, card, [FormalCheckIn(
            requirement_id=profile.formal_requirements[0].id, result=CheckResult.UNKNOWN,
            alternatives=[AlternativeResultIn(key="s.experience.alt1", result=CheckResult.UNKNOWN)])])


# --- Этап проверки --------------------------------------------------------------

def test_interview_requirement_does_not_affect_resume_result(session):
    """Обязательное требование этапа interview (знание закона) не делает итог разбора резюме unknown."""
    candidate = make_candidate(session, "hr-9004", text=TEXT, is_synthetic=True)
    card = add_card(session, candidate, ["Базы данных"])
    text_row = repo.get_current_text(session, candidate.id)
    profile = repo.create_requirement_profile(
        session, position_id=position(session, "hr-consultant").id, created_by="test", competencies=[],
        formal_requirements=[
            FormalRequirementIn(key="s.level", kind=FormalRequirementKind.EDUCATION_LEVEL, description="Высшее",
                                params={"schema_version": "0.1", "alternatives": [{"key": "s.level.alt1", "level": "высшее"}]},
                                verification=VerificationMethod.RESUME, **TEAM),
            FormalRequirementIn(key="s.law", kind=FormalRequirementKind.KNOWLEDGE, description="Знание 25-ФЗ",
                                verification=VerificationMethod.INTERVIEW, **TEAM),
        ])
    level_req, law_req = profile.formal_requirements
    assert (level_req.check_stage, law_req.check_stage) == (CheckStage.SCREENING, CheckStage.INTERVIEW)
    assessment = save(session, candidate, profile, card, [
        FormalCheckIn(requirement_id=level_req.id, result=CheckResult.MET, evidence=[quote(text_row, "Высшее образование")]),
    ])
    assert assessment.formal_result == CheckResult.MET


def test_interview_row_cannot_be_checked_at_screening():
    with pytest.raises(ValidationError, match="не проверяется на этапе screening"):
        IndicatorIn(key="x.01", text="пунктуальность", verification=VerificationMethod.INTERVIEW,
                    check_stage=CheckStage.SCREENING, **TEAM)


def test_database_rejects_interview_row_at_screening(session):
    profile = make_profile(session)
    with pytest.raises(IntegrityError, match="ck_competency_indicators_check_stage_verification"):
        with session.begin_nested():
            session.execute(
                text("INSERT INTO competency_indicators (competency_id, key, text, verification, check_stage, origin, note)"
                     " VALUES (:c, 'x.01', 'пунктуальность', 'interview', 'screening', 'team', 'тест')"),
                {"c": profile.competencies[0].id},
            )


# --- params 0.1 ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("kind", "params", "message"),
    [
        (FormalRequirementKind.EXPERIENCE, {"scope": "total_commercial", "minimum_defined": False}, "schema_version"),
        (FormalRequirementKind.EXPERIENCE, {"schema_version": "99.0", "scope": "total_commercial", "minimum_defined": False},
         "schema_version"),
        (FormalRequirementKind.EXPERIENCE, {"schema_version": "0.1", "scope": "total_commercial", "minimum_defined": True},
         "min_months"),
        (FormalRequirementKind.EXPERIENCE, {"schema_version": "0.1", "scope": "relevant_role", "minimum_defined": False},
         "relevance_hint"),
        (FormalRequirementKind.EXPERIENCE, {"schema_version": "0.1", "scope": "total_commercial", "minimum_defined": False,
                                            "min_years": 2}, "min_years"),
        (FormalRequirementKind.EDUCATION_LEVEL, {"schema_version": "0.1", "alternatives": [{"key": "a", "level": "бакалавр"}]},
         "level"),
        (FormalRequirementKind.EDUCATION_LEVEL, {"schema_version": "0.1", "alternatives": [
            {"key": "a", "level": "высшее"}, {"key": "a", "level": "высшее"}]}, "повторяются ключи альтернатив"),
        (FormalRequirementKind.EDUCATION_FIELD, {"schema_version": "0.1", "alternatives": [
            {"key": "a", "degree_fields": ["ГМУ"], "retraining_fields": ["ГМУ"]}]}, "ровно один"),
    ],
)
def test_params_outside_format_are_rejected(kind, params, message):
    with pytest.raises(ValidationError, match=message):
        FormalRequirementIn(key="x.req", kind=kind, description="x", params=params,
                            verification=VerificationMethod.RESUME, **TEAM)


def test_requires_requirement_must_point_to_education_level(session):
    field = FormalRequirementIn(
        key="x.field", kind=FormalRequirementKind.EDUCATION_FIELD, description="ГМУ",
        params={"schema_version": "0.1", "alternatives": [{"key": "x.field.alt1", "degree_fields": ["ГМУ"]}],
                "requires_requirement": "x.level"},
        verification=VerificationMethod.DOCUMENTS, **TEAM)
    with pytest.raises(repo.RepositoryError, match="x.level"):
        repo.create_requirement_profile(session, position_id=position(session).id, created_by="test",
                                        formal_requirements=[field], competencies=[])


def test_competency_without_params_rules_still_loads():
    """knowledge/other без правила — пустой params допустим: проверяет человек."""
    row = FormalRequirementIn(key="x.law", kind=FormalRequirementKind.KNOWLEDGE, description="25-ФЗ",
                              verification=VerificationMethod.INTERVIEW, **TEAM)
    assert row.check_stage == CheckStage.INTERVIEW
    competency = CompetencyIn(key="x.C", code="C", name="C", **TEAM, indicators=[
        IndicatorIn(key="x.C.01", text="умеет", verification=VerificationMethod.DOCUMENTS, **TEAM)])
    assert competency.indicators[0].check_stage == CheckStage.SCREENING
