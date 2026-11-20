import pytest
from pydantic import ValidationError

from app.assessment.applicability import Policy, resolve_applicability


@pytest.mark.parametrize('title,status,reason', [
    ('Сметчик', 'mismatch', 'different_role'),
    ('  СМЕТЧИК  ', 'mismatch', 'different_role'),
    ('Начальник отдела внутреннего финансового контроля, аудита и закупок', 'mismatch', 'different_role'),
    (None, 'unresolved', 'missing_posting'),
    ('Консультант отдела кадровой работы', 'unresolved', 'unreviewed_mapping'),
    ('Консультант сектора подбора кадров', 'unresolved', 'unreviewed_mapping'),
    ('Помощник сметчика', 'unresolved', 'unreviewed_mapping'),
])
def test_default_policy_is_conservative(title, status, reason):
    result = resolve_applicability('hr-consultant', title)
    assert result.status == status
    assert result.reason == reason
    assert result.explanation and result.explanation != result.reason
    assert result.policy_version and len(result.policy_hash) == 64


def test_policy_not_applied_to_other_positions():
    assert resolve_applicability('python-dev', 'Сметчик') is None


def test_confirmed_requires_explicit_reviewed_mapping():
    policy = Policy.model_validate({
        'version': 'test-1', 'position_code': 'hr-consultant',
        'rules': [{'posting_title': 'Консультант отдела кадровой работы',
                   'status': 'confirmed', 'reason': 'reviewed_mapping',
                   'source': 'decision-123', 'responsible': 'HR reviewer'}],
    })
    assert resolve_applicability('hr-consultant', 'Консультант отдела кадровой работы', policy=policy).status == 'confirmed'
    assert resolve_applicability('hr-consultant', None, policy=policy).status == 'unresolved'


def test_policy_rejects_ambiguity_and_unknown_fields():
    rule = dict(posting_title='Сметчик', status='mismatch', reason='different_role',
                source='ingest-02', responsible='David')
    with pytest.raises(ValidationError):
        Policy(version='1', position_code='hr-consultant', rules=[rule, {**rule, 'posting_title': ' СМЕТЧИК '}])
    with pytest.raises(ValidationError):
        Policy(version='1', position_code='hr-consultant', rules=[rule], typo=True)


def test_fingerprint_tracks_inputs_and_policy():
    first = resolve_applicability('hr-consultant', 'Сметчик')
    second = resolve_applicability('hr-consultant', None)
    assert first.input_hash != second.input_hash
    assert first.policy_hash == second.policy_hash
