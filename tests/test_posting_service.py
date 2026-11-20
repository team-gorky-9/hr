import pytest
from app.db import repository as repo
from app.db.enums import ApplicationSource
from app.postings.service import resolve_application, create_snapshot, read_snapshot
from tests import factories as f
from tests.posting_service_helpers import response, registry

def test_mapping_selects_profile_before_imported_vacancy(session):
    candidate = f.make_candidate(session, 'mapping-target')
    profile = f.approve(session, f.make_profile(session, 'python-dev'))
    app = response(session, candidate)
    result = resolve_application(session, app.id, registry=registry())
    assert result.ready and result.position_code == 'python-dev'
    assert result.profile_id == profile.id and result.profile_version == profile.version
    assert app.vacancy_id == f.vacancy(session, 'hr-consultant').id

@pytest.mark.parametrize('state,reason', [('needs_review','needs_review'), ('no_matching_position','no_matching_position')])
def test_nonconfirmed_has_no_target_profile(session, state, reason):
    candidate = f.make_candidate(session, 'mapping-pending')
    f.approve(session, f.make_profile(session, 'python-dev'))
    app = response(session, candidate)
    result = resolve_application(session, app.id, registry=registry(state=state))
    assert not result.ready and result.profile_id is None and result.reason == reason

def test_missing_profile_preserves_confirmed_mapping(session):
    candidate = f.make_candidate(session, 'mapping-profile')
    app = response(session, candidate)
    result = resolve_application(session, app.id, registry=registry())
    assert result.mapping.decision_state == 'confirmed'
    assert result.reason == 'no_approved_profile' and result.profile_id is None

def test_history_cannot_become_primary_or_snapshot_response(session):
    candidate = f.make_candidate(session, 'mapping-history')
    app = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.HISTORY,
        external_position_title='Publication')
    assert resolve_application(session, app.id, registry=registry()).reason == 'not_response'
    with pytest.raises(ValueError, match='response'):
        create_snapshot(session, [app.id], registry=registry())

def test_snapshot_frozen_after_registry_and_profile_changes(session):
    candidate = f.make_candidate(session, 'mapping-frozen')
    profile = f.approve(session, f.make_profile(session, 'python-dev'))
    app = response(session, candidate)
    snapshot = create_snapshot(session, [app.id, app.id], registry=registry())
    assert snapshot['response_count'] == 1
    assert snapshot['rows'][0]['resolution']['profile_id'] == str(profile.id)
    pending = resolve_application(session, app.id, registry=registry(state='needs_review', version='test-v2'))
    assert not pending.ready
    replacement = f.approve(session, f.make_profile(session, 'python-dev', version=2))
    assert replacement.id != profile.id
    assert read_snapshot(session, snapshot['snapshot_id']) == snapshot


def test_snapshot_counts_distinguish_decisions_readiness_and_records(session):
    rules, ids = [], []
    for index, state in enumerate(('confirmed', 'needs_review', 'no_matching_position')):
        candidate = f.make_candidate(session, f'counts-{index}')
        title = f'Publication {index}'
        ids.append(response(session, candidate, title=title).id)
        rule = registry(title=title, state=state).rules[0].model_copy(update={'id': f'rule-{index}'})
        rules.append(rule)
    merged = registry().model_copy(update={'rules': tuple(rules)})
    saved = create_snapshot(session, ids, registry=merged)
    assert saved['decision_counts'] == {'confirmed': 1, 'needs_review': 1, 'no_matching_position': 1}
    assert saved['ready_count'] == 0 and saved['blocked_count'] == 3
    assert saved['reason_counts'] == {'no_approved_profile': 1, 'needs_review': 1, 'no_matching_position': 1}
