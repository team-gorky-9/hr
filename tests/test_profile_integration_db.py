"""Real PostgreSQL integration. Standard suite requires TEST_DATABASE_URL + pgvector."""
import pytest
from sqlalchemy import select, func

from app.ai.fake import FakeLLMClient
from app.assessment.errors import AssessmentDomainError
from app.assessment.orchestration import assess_in_context
from app.assessment.service import assess_candidate
from app.assessment.version import ALGORITHM_VERSION
from app.api.services import get_application, get_comparison
from app.db import repository as repo
from app.db.enums import ApplicationSource, CheckResult, VerificationMethod, Channel
from app.db.models import Assessment, AuditLog, CompetencyIndicator, Vacancy, Application
from app.schemas.requirements import CompetencyIn, IndicatorIn
from tests import factories as f


@pytest.mark.parametrize('title,reason,status', [
    ('Сметчик', 'different_role', 'not_applicable'),
    ('Начальник отдела внутреннего финансового контроля, аудита и закупок', 'different_role', 'not_applicable'),
    (None, 'missing_posting', 'mapping_required'),
])
def test_mismatched_primary_is_audited_and_comparison_stays_explicit(session, title, reason, status):
    candidate = f.make_candidate(session, 'hr-0881')
    profile = f.approve(session, f.make_profile(session))
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
        vacancy_id=f.vacancy(session, 'hr-consultant').id, posting_title=title)
    llm = FakeLLMClient(lambda *args: {})
    skipped = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
        purpose='primary', application_id=application.id, as_of='2026-11')
    assert skipped['status'] == 'skipped' and skipped['reason'] == reason
    assert llm.calls == [] and llm.prompts == []
    assert session.scalar(select(func.count()).select_from(Assessment)) == 0
    assert application.current_stage_code == 'new'
    compared = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
        purpose='comparison', application_id=application.id, as_of='2026-11')
    assert compared['status'] == 'ok'
    assert get_application(session, application.id).assessment is None
    assert get_application(session, application.id).assessment_status == status
    comparison = get_comparison(session, application.id, profile.id)
    assert comparison.purpose == 'comparison' and comparison.assessment.assessment_id
    previous_calls = len(llm.prompts)
    reused = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
        purpose='comparison', application_id=application.id, as_of='2026-11')
    assert reused['reused'] and len(llm.prompts) == previous_calls
    assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_type == 'assessment_run')) == 3


def test_same_as_roundtrip_and_typed_evidence(session):
    candidate = f.make_candidate(session, 'py-0882', text='🙂 Писал SQL. Не писал SQL.', is_synthetic=True)
    team = dict(origin='team', note='synthetic test')
    profile = repo.create_requirement_profile(session, position_id=f.position(session).id, created_by='test',
        is_synthetic=True, formal_requirements=[], competencies=[CompetencyIn(key='c', code='C', name='SQL',
            indicators=[IndicatorIn(key='a', text='SQL', verification='resume', same_as='g', is_mandatory=False, **team),
                        IndicatorIn(key='b', text='SQL', verification='resume', same_as='g', **team)], **team)])
    assert session.scalar(select(CompetencyIndicator).where(CompetencyIndicator.key == 'a')).same_as == 'g'
    def answer(role, schema, system, user):
        if schema == 'CompetencyExtraction':
            return {'indicators': [dict(indicator_key='a', status='confirmed', quote='Писал SQL.'),
                                   dict(indicator_key='b', status='contradicted', quote='Не писал SQL.')]}
        return {}
    assessment_id = assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id,
                                     llm=FakeLLMClient(answer), mode='technical', as_of='2026-11')
    assessment = session.get(Assessment, assessment_id)
    assert assessment.algorithm_version == ALGORITHM_VERSION
    assert assessment.calculation_as_of == '2026-11'
    score = assessment.competency_scores[0]
    assert score.details['mandatory']['total'] == 1
    assert score.details['mandatory']['contradicted'] == 1
    assert score.details['groups'][0]['manual_review']
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=f.vacancy(session).id)
    result = get_comparison(session, application.id, profile.id)
    quotes = result.assessment.competency_scores[0].details.indicators[0].evidence
    assert quotes[0].start == 2 and quotes[0].utf16_start == 3
    assert result.assessment.competency_summary.mandatory.total == 1
    from app.schemas.assessment import CompetencyScoreIn
    invalid = CompetencyScoreIn(competency_id=profile.competencies[0].id, details=score.details)
    invalid.details.mandatory.total = 2
    with pytest.raises(repo.RepositoryError, match='counters'):
        repo.save_assessment(session, candidate_id=candidate.id, profile_id=profile.id,
            card_id=assessment.card_id, model='test', formal_checks=[], competency_scores=[invalid])
    invalid.details.mandatory.total = 1
    invalid.details.indicators[0].evidence[0].start = 0
    with pytest.raises(repo.RepositoryError):
        repo.save_assessment(session, candidate_id=candidate.id, profile_id=profile.id,
            card_id=assessment.card_id, model='test', formal_checks=[], competency_scores=[invalid])


def test_contours_checked_before_any_model_call(session):
    real = f.make_candidate(session, 'py-0883')
    profile = f.make_profile(session, is_synthetic=True)
    llm = FakeLLMClient(lambda *args: {})
    with pytest.raises(AssessmentDomainError) as error:
        assess_candidate(session, candidate_id=real.id, profile_id=profile.id, llm=llm, mode='technical')
    assert error.value.reason == 'candidate_contour'
    assert llm.prompts == []


def test_technical_allows_real_draft_for_synthetic_candidate(session):
    candidate = f.make_candidate(session, 'py-0884', is_synthetic=True)
    profile = f.make_profile(session)
    assessment_id = assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id,
        llm=FakeLLMClient(lambda *args: {}), mode='technical')
    old = session.get(Assessment, assessment_id)
    updated = repo.confirm_formal_check(session, assessment_id=assessment_id,
        requirement_id=profile.formal_requirements[0].id, result=CheckResult.MET,
        basis=VerificationMethod.DOCUMENTS, actor_user_id=f.make_user(session).id, comment='Тестовый диплом')
    assert updated.algorithm_version == old.algorithm_version
    assert updated.calculation_as_of == old.calculation_as_of
    assert updated.competency_scores[0].details == old.competency_scores[0].details
    assert updated.version == old.version + 1


def test_invalid_group_rejected_before_profile_write(session):
    team = dict(origin='team', note='test')
    competencies = [CompetencyIn(key=f'c{n}', code=f'C{n}', name='test', **team,
        indicators=[IndicatorIn(key=f'i{n}', text='SQL', verification='resume', same_as='g', **team)]) for n in (1, 2)]
    with pytest.raises(repo.RepositoryError, match='same_as'):
        repo.create_requirement_profile(session, position_id=f.position(session).id, created_by='test',
            formal_requirements=[], competencies=competencies)


def test_extraction_call_survives_later_assessment_failure_for_audit(session):
    from app.ai.errors import LLMUnavailableError
    candidate = f.make_candidate(session, 'py-0885', is_synthetic=True)
    profile = f.make_profile(session, is_synthetic=True)
    def answer(role, schema, system, user):
        return {} if schema == 'CandidateCard' else LLMUnavailableError('test timeout')
    llm = FakeLLMClient(answer)
    with pytest.raises(LLMUnavailableError):
        assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm, mode='technical')
    assert [call.role for call in llm.calls] == ['extract', 'assess']


def test_confirmed_application_does_not_inherit_other_application_mismatch(session):
    from app.assessment.applicability import Policy
    candidate = f.make_candidate(session, 'hr-0886')
    profile = f.approve(session, f.make_profile(session))
    vacancy = f.vacancy(session, 'hr-consultant')
    second_vacancy = Vacancy(position_id=vacancy.position_id, title='Другой отклик того же кандидата', channel=Channel.HH_RU)
    session.add(second_vacancy)
    session.flush()
    first = repo.create_application(session, candidate_id=candidate.id, vacancy_id=vacancy.id,
                                     source=ApplicationSource.RESPONSE, posting_title='Сметчик')
    second = repo.create_application(session, candidate_id=candidate.id, vacancy_id=second_vacancy.id,
                                     source=ApplicationSource.RESPONSE, posting_title='Подтверждённая тестовая публикация')
    policy = Policy(version='test-1', position_code='hr-consultant', rules=[
        dict(posting_title='Сметчик', status='mismatch', reason='different_role', source='test', responsible='test'),
        dict(posting_title=second.posting_title, status='confirmed', reason='reviewed_mapping',
             source='synthetic mapping decision', responsible='test reviewer')])
    llm = FakeLLMClient(lambda *args: {})
    one = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
                            application_id=first.id, policy=policy)
    two = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
                            application_id=second.id, policy=policy)
    assert one['status'] == 'skipped' and two['status'] == 'ok'
    assert two['formal_result'] == 'unknown'  # mapping is not qualification evidence
    assert session.scalar(select(func.count()).select_from(Application)) == 2
    previous = len(llm.prompts)
    second.posting_title = 'Сметчик'
    changed = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
                                application_id=second.id, policy=policy)
    assert changed['status'] == 'skipped' and len(llm.prompts) == previous
    assert changed['applicability']['input_hash'] != two['applicability']['input_hash']


@pytest.mark.parametrize('mode', ['operational', 'technical'])
def test_real_candidate_draft_comparison_cannot_bypass_approval(session, mode):
    candidate = f.make_candidate(session, 'hr-0887')
    profile = f.make_profile(session)
    llm = FakeLLMClient(lambda *args: {})
    with pytest.raises(AssessmentDomainError):
        assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
                           purpose='comparison', mode=mode)
    assert llm.prompts == []


def test_batch_with_no_applicable_records_does_not_even_build_model_client(session, monkeypatch, capsys):
    import json
    from sqlalchemy.orm import Session
    from app.assessment import __main__ as cli
    from app.db import session as db_session
    from app.ai.errors import LLMUnavailableError
    candidate = f.make_candidate(session, 'hr-0888')
    f.approve(session, f.make_profile(session))
    repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
        vacancy_id=f.vacancy(session, 'hr-consultant').id, posting_title='Сметчик')
    connection = session.connection()
    monkeypatch.setattr(db_session, 'SessionLocal', lambda: Session(bind=connection, join_transaction_mode='create_savepoint'))
    called = []
    def forbidden():
        called.append(True)
        raise LLMUnavailableError('should not configure model for skipped batch')
    monkeypatch.setattr(cli, 'build_client', forbidden)
    assert cli.main(['batch', '--position-code', 'hr-consultant', '--as-of', '2026-11']) == 0
    assert called == []
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1 and rows[0]['status'] == 'skipped'
