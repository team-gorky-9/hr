import uuid
from types import SimpleNamespace as Row

import pytest

from app.ai.fake import FakeLLMClient
from app.assessment.service import _CheckDraft, _apply_basis, _assess_competency, _education_check, _to_check_in
from app.assessment.llm_schemas import FormalExtraction
from app.assessment.rules import parse_rule
from app.db.enums import CheckResult
from app.db.models import CandidateText, FormalRequirement
from app.schemas.card import Evidence
from app.schemas.requirements import IndicatorIn
from app.assessment.errors import RuleUnsupportedError


def test_document_verification_keeps_quoted_met():
    evidence = Evidence(candidate_text_id=uuid.uuid4(), quote='Diploma', start=0, end=7)
    draft = _CheckDraft(Row(verification='documents'), CheckResult.MET, [evidence])
    assert _apply_basis(draft).result == CheckResult.MET


def test_alternatives_keep_their_own_evidence():
    text = CandidateText(id=uuid.uuid4(), text='Higher education.')
    requirement = FormalRequirement(id=uuid.uuid4(), key='edu', kind='education_level',
        params={'schema_version': '0.1', 'alternatives': [{'key': 'edu.a', 'level': 'высшее'}]},
        verification='documents')
    rule = parse_rule(requirement.key, requirement.kind, requirement.params, requirement.verification)
    extraction = FormalExtraction(alternatives=[dict(alternative_key='edu.a', status='confirmed', quote=text.text)])
    check = _to_check_in(_education_check(requirement, rule, extraction, text))
    assert [(a.key, a.result, a.evidence[0].quote) for a in check.alternatives] == [('edu.a', 'met', text.text)]


def test_stage_is_read_directly_and_criteria_reach_model():
    text = CandidateText(id=uuid.uuid4(), text='Built SQL pipelines.')
    def indicator(key, stage):
        return Row(key=key, text=key, verification='resume', check_stage=stage,
                   excluded_from_scoring=False, same_as=None, is_mandatory=True,
                   acceptance={'met': 'Only production ETL counts'})
    competency = Row(id=uuid.uuid4(), name='Data', indicators=[indicator('sql', 'screening'), indicator('law', 'interview')])
    llm = FakeLLMClient(lambda *args: {'indicators': [{'indicator_key': 'sql', 'status': 'confirmed', 'quote': text.text}]})
    score = _assess_competency(competency, text, llm, 'test')
    assert 'Only production ETL counts' in llm.prompts[0][1]
    assert '"indicator_key": "law"' not in llm.prompts[0][1]
    assert score.details.mandatory.total == 1
    assert score.details.on_interview == 1
    assert score.details.indicators[0].evidence[0].quote == text.text


def test_indicator_schema_accepts_group_and_rejects_excluded_member():
    args = dict(key='i', text='SQL', origin='team', note='Decision', verification='resume', same_as='g')
    assert IndicatorIn(**args).same_as == 'g'
    with pytest.raises(ValueError):
        IndicatorIn(**args, excluded_from_scoring=True)


def test_alternative_can_require_multiple_fragments():
    text = CandidateText(id=uuid.uuid4(), text='Degree. Retraining.')
    requirement = FormalRequirement(id=uuid.uuid4(), key='edu', kind='education_level',
        params={'schema_version': '0.1', 'alternatives': [{'key': 'edu.a', 'level': 'высшее'}]}, verification='documents')
    rule = parse_rule(requirement.key, requirement.kind, requirement.params, requirement.verification)
    extraction = FormalExtraction(alternatives=[dict(alternative_key='edu.a', status='confirmed',
        quotes=[{'quote': 'Degree.'}, {'quote': 'Retraining.'}])])
    check = _to_check_in(_education_check(requirement, rule, extraction, text))
    assert [e.start for e in check.alternatives[0].evidence] == [0, 8]


@pytest.mark.parametrize('kind,params', [
    ('knowledge', {'schema_version': '99.0'}),
    ('other', {'schema_version': '0.1', 'typo': True}),
    ('experience', {'schema_version': '0.1', 'scope': 'relevant_role', 'minimum_defined': False}),
])
def test_invalid_rule_is_rejected_in_every_stage(kind, params):
    with pytest.raises(RuleUnsupportedError):
        parse_rule('r', kind, params, 'interview')


def test_full_card_dates_keep_inclusive_calendar_month_convention():
    from app.assessment.experience import Period, commercial_months, parse_point
    months = commercial_months([Period('2021-01-31', '2023-12-01', kind='work')], as_of='2026-11')
    assert months.low == months.high == 36
    assert parse_point('2023-02-30') is None
