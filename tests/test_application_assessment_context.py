import uuid
from types import SimpleNamespace as Row

import pytest

from app.assessment.errors import AssessmentDomainError
from app.assessment.orchestration import preflight_application
from app.api.services import AssessmentState, application_state
from app.api.schemas import AssessmentStatus


@pytest.mark.parametrize('title,status', [('Сметчик', 'not_applicable'), (None, 'mapping_required')])
def test_cached_pair_cannot_appear_as_primary_assessment(title, status):
    state = AssessmentState(AssessmentStatus.READY, Row(formal_result='not_met'))
    result, mapping = application_state(state, 'hr-consultant', title)
    assert result.status == status
    assert result.assessment is None
    assert mapping.status in {'mismatch', 'unresolved'}
    assert state.assessment is not None  # comparison still exists, not deleted


def test_wrong_application_owner_is_rejected_before_scoring():
    with pytest.raises(AssessmentDomainError, match='принадлежит'):
        preflight_application(Row(candidate_id=uuid.uuid4(), source='response'),
                              candidate_id=uuid.uuid4(), position_code='hr-consultant',
                              application_position_id=1, target_position_id=1, purpose='primary')


def test_explicit_comparison_does_not_require_title_match():
    cid = uuid.uuid4()
    app = Row(candidate_id=cid, source='response', posting_title='Сметчик')
    mapping = preflight_application(app, candidate_id=cid, position_code='hr-consultant',
        application_position_id=2, target_position_id=1, purpose='comparison')
    assert mapping.status == 'mismatch'


def test_history_is_not_primary_even_when_title_is_known():
    cid = uuid.uuid4()
    with pytest.raises(AssessmentDomainError) as error:
        preflight_application(Row(candidate_id=cid, source='history', posting_title='Сметчик'),
            candidate_id=cid, position_code='hr-consultant', application_position_id=None,
            target_position_id=1, purpose='primary')
    assert error.value.reason == 'not_primary_application'
