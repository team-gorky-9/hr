"""Controlled replies for the 41 addressed checks, not an extraction-quality oracle.

Education replies use existing expectations (as agreed with Ilya). Experience input
uses annotated card values and quotes; months and the target result are never fed to
the evaluator. Missing expectations for other keys are not interpreted as unknown.
"""
import copy
import json
import re
import uuid
from pathlib import Path

from app.db.models import CandidateText, FormalRequirement, RequirementProfile

ROOT = Path(__file__).resolve().parents[1] / 'fixtures/requirement_profiles'
PACKAGE = json.loads((ROOT / 'profiles.draft.json').read_text(encoding='utf-8'))
CASES_DOC = json.loads((ROOT / 'synthetic/cases.json').read_text(encoding='utf-8'))
CASES = CASES_DOC['cases']
PROFILES = [*PACKAGE['profiles'], CASES_DOC['synthetic_profile']]


def case_profile(case):
    source = next(p for p in PROFILES if any(r['key'] == case['rule_key'] for r in p['formal_requirements']))
    rows = []
    for n, data in enumerate(source['formal_requirements']):
        data = copy.deepcopy(data)
        if data['key'] == case['rule_key']:
            data['params'] = case['expected'].get('params_override', data['params'])
        rows.append(FormalRequirement(id=uuid.uuid5(uuid.NAMESPACE_URL, data['key']), key=data['key'],
            kind=data['kind'], description=data['text'], params=data['params'],
            verification=data['verification'], check_stage=data['check_stage'],
            acceptance=data.get('acceptance', {}), is_mandatory=data['is_mandatory'], sort_order=n))
    return RequirementProfile(formal_requirements=rows, competencies=[]), CandidateText(
        id=uuid.UUID(case['candidate_text_id']), text=case['text'])


def indexes_for_path(case, prefix):
    return sorted({i for item in case.get('card_evidence', []) if item['path'].startswith(prefix)
                   for i in item['evidence_indexes']})


def controlled_reply(case, profile):
    expected = case['expected']
    target = next(r for r in profile.formal_requirements if r.key == case['rule_key'])
    evidence = case['evidence']
    if target.kind.startswith('education'):
        answers = []
        result_map = {'met': 'confirmed', 'not_met': 'refuted', 'unknown': 'no_info'}
        for row in profile.formal_requirements:
            if not row.kind.startswith('education'):
                continue
            target_row = row.key == target.key
            alternatives = row.params['alternatives']
            for n, alt in enumerate(alternatives):
                if target_row:
                    status = expected.get('alternative_results', {}).get(alt['key'])
                    if status is None:
                        status = expected['result']
                        if status == 'met' and len(alternatives) > 1:
                            selected = 1 if 'старших' in case['text'].lower() else 0
                            status = 'met' if n == selected else 'unknown'
                    idx = expected.get('alternative_evidence_indexes', {}).get(alt['key'],
                        expected.get('formal_evidence_indexes', []))
                elif row.key == target.params.get('requires_requirement'):
                    # All four existing field cases explicitly state completed higher education.
                    assert any(e.get('level') == 'высшее' for e in case['card'].get('education', []))
                    status, idx = 'met', indexes_for_path(case, '/education/0/level')
                else:
                    status, idx = 'unknown', []
                answers.append({'alternative_key': alt['key'], 'status': result_map[status],
                    'quotes': [{'quote': evidence[i]['quote'],
                                'context_before': case['text'][:evidence[i]['start']]} for i in idx]})
        return {'alternatives': answers}
    periods = []
    for n, row in enumerate(case['card'].get('experience', [])):
        idx = indexes_for_path(case, f'/experience/{n}/')
        if not idx:
            continue
        quote = evidence[idx[0]]['quote']
        kind = row.get('kind')
        for limitation in case.get('card_limitations', []):
            if set(idx) & set(limitation['evidence_indexes']):
                match = re.search(r'Тип периода: (work|contract|project|internship)', limitation['fact'])
                if match:
                    kind = match[1]
        # Older cards have no kind, but their explicit quoted commercial/employer
        # context is part of the controlled extraction reply, not a new product rule.
        if kind is None and 'period_kinds' not in expected:
            if 'коммерческ' in quote.lower() or 'на работе в компании' in quote.lower():
                kind = 'work'
            elif 'проект' in quote.lower():
                kind = 'project'
        dates = re.findall(r'\b(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?\b', quote)
        periods.append(dict(start=row.get('start') or (dates[0] if dates else None),
            end=row.get('end') or (dates[1] if len(dates) > 1 else None), is_current=row.get('is_current', False),
            kind=kind or 'unknown', relevant=target.params['scope'] == 'relevant_role', quote=quote,
            context_before=case['text'][:evidence[idx[0]]['start']]))
    statement = None
    if case['card'].get('experience_years') is not None:
        idx = indexes_for_path(case, '/experience_years')
        assert idx, case['id']
        quote = evidence[idx[0]]['quote']
        months = round(case['card']['experience_years'] * 12)
        statement = dict(years=months // 12, months=months % 12,
                         commercial='коммерческ' in quote.lower(), quote=quote)
    no_experience = next((e['quote'] for e in evidence if 'опыта' in e['quote'].lower() and 'нет' in e['quote'].lower()), None)
    return dict(periods=periods, statement=statement, no_experience_quote=no_experience)
