import pytest
from sqlalchemy.exc import IntegrityError

from app.db import repository as repo
from app.db.enums import CheckResult, RequirementStatus
from app.schemas.assessment import CompetencyScoreIn, FormalCheckIn
from app.schemas.card import Evidence
from tests.factories import add_card, make_candidate, make_profile

TEXT = "Высшее образование, Юриспруденция, 2015. Работал с базами данных и электронной почтой."


def quote(text_row, fragment: str) -> Evidence:
    start = text_row.text.index(fragment)
    return Evidence(candidate_text_id=text_row.id, quote=fragment, start=start, end=start + len(fragment))


def setup(session, code="hr-0200"):
    candidate = make_candidate(session, code, text=TEXT)
    card = add_card(session, candidate, ["Базы данных"])
    profile = make_profile(session)
    return candidate, card, profile, repo.get_current_text(session, candidate.id)


def test_assessment_with_verified_quotes(session):
    candidate, card, profile, text_row = setup(session)
    level_req, field_req = profile.formal_requirements
    itk = profile.competencies[0]

    assessment = repo.save_assessment(
        session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="test-model",
        formal_checks=[
            FormalCheckIn(requirement_id=level_req.id, result=CheckResult.MET,
                          evidence=[quote(text_row, "Высшее образование")]),
            FormalCheckIn(requirement_id=field_req.id, result=CheckResult.MET,
                          evidence=[quote(text_row, "Юриспруденция")]),
        ],
        competency_scores=[
            CompetencyScoreIn(competency_id=itk.id, level=70,
                              evidence=[quote(text_row, "Работал с базами данных")]),
        ],
        overall_score=70,
    )
    assert assessment.formal_result == CheckResult.MET
    assert assessment.competency_scores[0].evidence[0]["quote"] == "Работал с базами данных"


def test_quote_not_in_text_is_rejected(session):
    candidate, card, profile, text_row = setup(session)
    fake = Evidence(candidate_text_id=text_row.id, quote="Опыт управления проектами", start=0, end=25)
    with pytest.raises(repo.EvidenceError):
        repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m", formal_checks=[],
            competency_scores=[CompetencyScoreIn(competency_id=profile.competencies[0].id, level=90, evidence=[fake])],
        )


def test_quote_from_another_candidate_is_rejected(session):
    candidate, card, profile, _ = setup(session)
    other = make_candidate(session, "hr-0201", text=TEXT)
    other_text = repo.get_current_text(session, other.id)
    with pytest.raises(repo.EvidenceError):
        repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m",
            formal_checks=[FormalCheckIn(requirement_id=profile.formal_requirements[0].id, result=CheckResult.MET,
                                         evidence=[quote(other_text, "Высшее образование")])],
            competency_scores=[],
        )


@pytest.mark.parametrize(
    ("level_result", "expected"),
    [(CheckResult.NOT_MET, CheckResult.NOT_MET), (CheckResult.UNKNOWN, CheckResult.UNKNOWN), (None, CheckResult.UNKNOWN)],
)
def test_formal_result_is_computed_by_code(session, level_result, expected):
    candidate, card, profile, _ = setup(session)
    checks = []
    if level_result is not None:
        checks.append(FormalCheckIn(requirement_id=profile.formal_requirements[0].id, result=level_result))
    # Необязательное требование (направление) не влияет на итог.
    checks.append(FormalCheckIn(requirement_id=profile.formal_requirements[1].id, result=CheckResult.NOT_MET))
    assessment = repo.save_assessment(
        session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m", formal_checks=checks, competency_scores=[]
    )
    assert assessment.formal_result == expected


def test_new_assessment_version_replaces_current(session):
    candidate, card, profile, _ = setup(session)
    kwargs = dict(candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m", formal_checks=[], competency_scores=[])
    first = repo.save_assessment(session, **kwargs)
    second = repo.save_assessment(session, **kwargs, prompt_version="v2")
    session.refresh(first)
    assert (first.is_current, second.is_current, second.version) == (False, True, 2)


def test_competency_from_other_profile_is_rejected(session):
    candidate, card, profile, _ = setup(session)
    other_profile = make_profile(session, "python-dev")
    with pytest.raises(repo.RepositoryError):
        repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m", formal_checks=[],
            competency_scores=[CompetencyScoreIn(competency_id=other_profile.competencies[0].id, level=50)],
        )


def test_only_one_approved_profile_per_position(session):
    first = make_profile(session)
    first.status = RequirementStatus.APPROVED
    session.flush()
    second = make_profile(session, version=2)  # черновик второй версии сохраняется
    second.status = RequirementStatus.APPROVED
    with pytest.raises(IntegrityError):
        session.flush()


def test_same_requirement_twice_is_rejected(session):
    candidate, card, profile, _ = setup(session)
    requirement_id = profile.formal_requirements[0].id
    with pytest.raises(repo.RepositoryError, match="дважды"):
        repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m",
            formal_checks=[FormalCheckIn(requirement_id=requirement_id, result=CheckResult.NOT_MET),
                           FormalCheckIn(requirement_id=requirement_id, result=CheckResult.MET)],
            competency_scores=[],
        )


def test_same_competency_twice_is_rejected(session):
    candidate, card, profile, _ = setup(session)
    competency_id = profile.competencies[0].id
    with pytest.raises(repo.RepositoryError, match="дважды"):
        repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m", formal_checks=[],
            competency_scores=[CompetencyScoreIn(competency_id=competency_id, level=40),
                               CompetencyScoreIn(competency_id=competency_id, level=90)],
        )


def test_met_on_requirement_checked_by_documents_is_stored_as_unknown(session):
    """Направление подготовки подтверждается дипломом: по резюме его не закрываем."""
    candidate, card, profile, text_row = setup(session)
    level_req, field_req = profile.formal_requirements
    field_req.is_mandatory = True
    session.flush()
    assessment = repo.save_assessment(
        session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m",
        formal_checks=[
            FormalCheckIn(requirement_id=level_req.id, result=CheckResult.MET,
                          evidence=[quote(text_row, "Высшее образование")]),
            FormalCheckIn(requirement_id=field_req.id, result=CheckResult.MET,
                          evidence=[quote(text_row, "Юриспруденция")]),
        ],
        competency_scores=[],
    )
    stored = {c.requirement_id: c.result for c in assessment.formal_checks}
    assert stored == {level_req.id: CheckResult.MET, field_req.id: CheckResult.UNKNOWN}
    assert assessment.formal_result == CheckResult.UNKNOWN
    assert assessment.formal_checks[1].evidence  # цитата сохраняется как основание для проверки


def test_not_met_on_requirement_checked_by_documents_stays(session):
    candidate, card, profile, _ = setup(session)
    field_req = profile.formal_requirements[1]
    field_req.is_mandatory = True
    session.flush()
    assessment = repo.save_assessment(
        session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m",
        formal_checks=[FormalCheckIn(requirement_id=field_req.id, result=CheckResult.NOT_MET)], competency_scores=[],
    )
    assert assessment.formal_result == CheckResult.NOT_MET


def test_quote_from_other_text_version_than_card_is_rejected(session):
    candidate, card, profile, old_text = setup(session)
    repo.add_candidate_text(session, candidate.id, text=TEXT + " Новая версия.", redaction_method="test-v2")
    new_text = repo.get_current_text(session, candidate.id)
    with pytest.raises(repo.EvidenceError, match="карточка"):
        repo.save_assessment(
            session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="m",
            formal_checks=[FormalCheckIn(requirement_id=profile.formal_requirements[0].id, result=CheckResult.MET,
                                         evidence=[quote(new_text, "Высшее образование")])],
            competency_scores=[],
        )
    assert card.candidate_text_id == old_text.id
