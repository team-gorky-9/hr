import pytest

from app.ai.fake import FakeLLMClient
from app.assessment.errors import RuleUnsupportedError
from app.assessment.evidence import resolve_quote
from app.assessment.rules import parse_rule
from app.assessment.service import _assess_formal
from scripts.profile_case_inputs import CASES, case_profile, controlled_reply


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_addressed_rule_against_independent_fixture(case):
    profile, text = case_profile(case)
    llm = FakeLLMClient(lambda *args: controlled_reply(case, profile))
    if case['expected']['result'] == 'processing_error':
        with pytest.raises(RuleUnsupportedError):
            {r.key: parse_rule(r.key, r.kind, r.params, r.verification) for r in profile.formal_requirements}
        assert llm.calls == []
        return
    rules = {r.key: parse_rule(r.key, r.kind, r.params, r.verification) for r in profile.formal_requirements}
    drafts = _assess_formal(profile, rules, text, llm, 'controlled-test', case.get('as_of', '2026-11'))
    target = next(d for d in drafts if d.requirement.key == case['rule_key'])
    assert target.result == case['expected']['result']
    for expected_key, actual_key in [('period_months_lower', 'months_low'), ('period_months_upper', 'months_high'),
                                     ('experience_conflict', 'conflict'), ('value_discrepancy', 'divergence')]:
        if expected_key in case['expected']:
            assert target.details.get(actual_key) == case['expected'][expected_key]
    if 'alternative_results' in case['expected']:
        assert {a.key: a.result for a in target.alternatives} == case['expected']['alternative_results']
    for marked in case['evidence']:
        found = resolve_quote(text.text, marked['quote'], candidate_text_id=text.id,
                              context_before=text.text[:marked['start']])
        assert found is not None
        assert (found.evidence.start, found.evidence.end) == (marked['start'], marked['end'])
