from app.ai.fake import FakeLLMClient
from app.assessment.orchestration import assess_in_context
from app.api.services import get_application, list_applications, ApplicationFilters
from app.api.schemas import Contour
from tests import factories as f
from tests.posting_service_helpers import registry, response

def test_primary_derives_profile_and_api_shows_same_decision(session, monkeypatch):
    from app.postings import service
    candidate = f.make_candidate(session, 'mapping-engine')
    profile = f.approve(session, f.make_profile(session, 'python-dev'))
    app = response(session, candidate)
    monkeypatch.setattr(service, 'get_default_registry', lambda: registry())
    llm = FakeLLMClient(lambda *args: {})
    result = assess_in_context(session, candidate_id=candidate.id, llm=llm,
        application_id=app.id, as_of='2026-11')
    assert result['status'] == 'ok' and result['profile_id'] == str(profile.id)
    detail = get_application(session, app.id)
    assert detail.target_position_code == 'python-dev'
    assert detail.vacancy.position_code == 'hr-consultant'
    assert detail.posting_resolution.profile_id == profile.id
    assert detail.assessment.assessment_id == result['assessment_id'] or str(detail.assessment.assessment_id) == result['assessment_id']
    listed = list_applications(session, app.vacancy_id, Contour.WORKING, ApplicationFilters())
    assert listed.items[0].posting_resolution == detail.posting_resolution
    assert listed.items[0].assessment_status == detail.assessment_status
    previous_calls = len(llm.prompts)
    monkeypatch.setattr(service, 'get_default_registry', lambda: registry(state='needs_review', version='test-v2'))
    revoked = assess_in_context(session, candidate_id=candidate.id, profile_id=profile.id, llm=llm,
        application_id=app.id, as_of='2026-11')
    assert revoked['status'] == 'skipped' and revoked['reason'] == 'needs_review'
    assert len(llm.prompts) == previous_calls
    assert get_application(session, app.id).assessment is None

def test_missing_context_skips_without_profile_or_llm(session, monkeypatch):
    from app.postings import service
    from app.db import repository as repo
    candidate = f.make_candidate(session, 'mapping-no-context')
    app = repo.create_application(session, candidate_id=candidate.id, source='response',
                                 vacancy_id=f.vacancy(session).id, posting_title='Publication')
    monkeypatch.setattr(service, 'get_default_registry', lambda: registry())
    llm = FakeLLMClient(lambda *args: {})
    result = assess_in_context(session, candidate_id=candidate.id, llm=llm, application_id=app.id)
    assert result['status'] == 'skipped' and result['reason'] == 'missing_context'
    assert result['profile_id'] is None and llm.prompts == []


def test_comparison_exposes_original_resolution_and_explicit_different_target(session, monkeypatch):
    from app.postings import service
    from app.api.services import get_comparison
    candidate = f.make_candidate(session, 'mapping-comparison')
    f.approve(session, f.make_profile(session, 'python-dev'))
    other = f.approve(session, f.make_profile(session, 'hr-consultant'))
    app = response(session, candidate)
    monkeypatch.setattr(service, 'get_default_registry', lambda: registry())
    result = get_comparison(session, app.id, other.id)
    assert result.purpose == 'comparison'
    assert result.posting_resolution.position_code == 'python-dev'
    assert result.target_position_code == 'hr-consultant'
    assert result.applicability.status == 'mismatch' and result.applicability.reason == 'different_target'
