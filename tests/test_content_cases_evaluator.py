"""Controlled extraction and routing checks for the separate 16 content examples.

Does not assert live-model semantic accuracy. Original manually labelled files stay unchanged.
"""
import json
import uuid
from types import SimpleNamespace as Row

import pytest

from app.ai.fake import FakeLLMClient
from app.assessment.rules import parse_rule
from app.assessment.service import _assess_competency, _assess_formal
from app.db.models import CandidateText, FormalRequirement, RequirementProfile
from scripts.profile_case_inputs import ROOT, PACKAGE

CONTENT = json.loads((ROOT / 'synthetic/content-cases.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('case', CONTENT, ids=lambda c: c['id'])
def test_content_target_criteria_and_stage(case):
    profile = next(p for p in PACKAGE['profiles'] if p['position_code'] == case['position_code'])
    text = CandidateText(id=uuid.uuid5(uuid.NAMESPACE_URL, case['id']), text=case['text'])
    formal = next((r for r in profile['formal_requirements'] if r['key'] == case['rule_key']), None)
    expected = case['expected']['result']
    if formal:
        row = FormalRequirement(id=uuid.uuid4(), key=formal['key'], kind=formal['kind'],
            description=formal['text'], params=formal['params'], check_stage=formal['check_stage'],
            verification=formal['verification'], acceptance=formal['acceptance'], sort_order=1)
        alternatives = []
        for n, alt in enumerate(row.params.get('alternatives', [])):
            selected = n == (1 if 'student' in case['id'] else 0)
            status = ('confirmed' if selected else 'no_info') if expected == 'met' else (
                'refuted' if expected == 'not_met' else 'no_info')
            alternatives.append(dict(alternative_key=alt['key'], status=status,
                                      quotes=[{'quote': e['quote']} for e in case['evidence']]))
        reply = {'alternatives': alternatives}
        if row.kind == 'experience':
            reply = {'periods': [{'kind': 'project' if case['id'] == 'content-personal-project' else 'work',
                'relevant': None if case['id'] == 'content-reporting-vague' else True,
                'quote': case['evidence'][0]['quote']}]}
        llm = FakeLLMClient(lambda *args: reply)
        result = _assess_formal(RequirementProfile(formal_requirements=[row]),
            {row.key: parse_rule(row.key, row.kind, row.params, row.verification)}, text, llm, 'content-test', '2026-11')[0]
        assert result.result == expected
        assert json.dumps(row.acceptance, ensure_ascii=False) in llm.prompts[0][1]
    else:
        group = next(c for c in profile['competencies'] if any(i['key'] == case['rule_key'] for i in c['indicators']))
        indicators = [Row(key=i['key'], text=i['text'], check_stage=i['check_stage'], verification=i['verification'],
            acceptance=i.get('acceptance', {}), is_mandatory=i['is_mandatory'], same_as=i.get('same_as'),
            excluded_from_scoring=i.get('excluded_from_scoring', False)) for i in group['indicators']]
        active = case['expected']['included_in_screening']
        answers = [] if not active else [dict(indicator_key=case['rule_key'],
            status={'met': 'confirmed', 'not_met': 'contradicted', 'unknown': 'no_info'}[expected],
            quote=case['evidence'][0]['quote'] if case['evidence'] else None)]
        llm = FakeLLMClient(lambda *args: {'indicators': answers})
        result = _assess_competency(Row(id=uuid.uuid4(), name=group['text'], indicators=indicators), text, llm, 'content-test')
        rows = {i.key: i for i in result.details.indicators}
        if not active:
            assert case['rule_key'] not in rows
        else:
            assert rows[case['rule_key']].status == {'met': 'confirmed', 'not_met': 'contradicted', 'unknown': 'no_info'}[expected]
            criteria = next(i.acceptance for i in indicators if i.key == case['rule_key'])
            assert json.dumps(criteria, ensure_ascii=False) in llm.prompts[0][1]
