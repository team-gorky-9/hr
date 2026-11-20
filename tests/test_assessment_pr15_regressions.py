"""Регрессии ревью PR 15: настоящая логика, контролируемые ответы LLM, без сети."""
import json
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError

from app.ai.errors import LLMInvalidResponseError
from app.ai.fake import FakeLLMClient
from app.api.services import resolve_states
from app.assessment.llm_schemas import keyed_competency, keyed_formal
from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.assessment.rules import parse_rule
from app.assessment.service import _assess_formal
from app.assessment.version import ALGORITHM_VERSION
from app.db import repository as repo
from scripts.approve_profile import approver
from scripts.profile_case_inputs import CASES, case_profile
from tests.test_ai_client import call, client


def evaluate(case_id, text_value, response):
    case = next(c for c in CASES if c['id'] == case_id)
    profile, text = case_profile(case)
    text.text = text_value
    rules = {r.key: parse_rule(r.key, r.kind, r.params, r.verification) for r in profile.formal_requirements}
    drafts = _assess_formal(profile, rules, text, FakeLLMClient(lambda *args: response),
                            ASSESS_PROMPT_VERSION, '2026-11')
    return next(d for d in drafts if d.requirement.key == case['rule_key'])


@pytest.mark.parametrize('quote', [
    'Опыт работы не указан. Диплома нет.',
    'Опыт работы не указан; диплома нет.',
    'Опыт работы есть, диплома нет.',
    'Опыт работы есть, но диплом отсутствует.',
    'Информация об опыте отсутствует.',
    'Нет проблем с опытом работы.',
    'Опыт работы не отсутствует.',
    'Опыт работы неизвестен и диплома нет.',
])
def test_unrelated_negation_does_not_refute_experience(quote):
    result = evaluate('py-relevant-unknown', quote, {'no_experience_quote': quote})
    assert result.result == 'unknown'
    assert result.evidence == []


@pytest.mark.parametrize('quote', [
    'Опыта нет.', 'Нет коммерческого опыта.', 'Без опыта работы.',
    'Не имею коммерческого опыта.', 'Опыт работы отсутствует.',
    'Опыта разработки на Python и работы с данными у меня нет.',
    'Отсутствует опыт работы.', 'Опыт работы: нет.',
])
def test_explicit_experience_negation_still_refutes(quote):
    result = evaluate('py-relevant-unknown', quote, {'no_experience_quote': quote})
    assert result.result == 'not_met'
    assert [q.quote for q in result.evidence] == [quote]


@pytest.mark.parametrize('reverse', [False, True])
def test_field_education_independent_of_quote_order(reverse):
    quotes = [{'quote': 'Прикладная информатика'}, {'quote': 'Высшее образование окончено'}]
    if reverse:
        quotes.reverse()
    response = {'alternatives': [
        {'alternative_key': 'py.education.alt1', 'status': 'confirmed', 'quotes': quotes},
        {'alternative_key': 'py.education.alt2', 'status': 'no_info'},
    ]}
    result = evaluate('py-education-met', 'Прикладная информатика; Высшее образование окончено', response)
    assert result.result == 'met'
    assert {q.quote for q in result.evidence} == {q['quote'] for q in quotes}


@pytest.mark.parametrize('reverse', [False, True])
def test_duplicate_alternative_preserves_all_evidence(reverse):
    items = [
        {'alternative_key': 'py.education.alt1', 'status': 'confirmed'},
        {'alternative_key': 'py.education.alt1', 'status': 'confirmed',
         'quotes': [{'quote': 'Прикладная информатика'}]},
        {'alternative_key': 'py.education.alt1', 'status': 'confirmed',
         'quote': 'Высшее образование окончено'},
    ]
    if reverse:
        items.reverse()
    items.append({'alternative_key': 'py.education.alt2', 'status': 'no_info'})
    result = evaluate('py-education-met', 'Прикладная информатика; Высшее образование окончено',
                      {'alternatives': items})
    assert result.result == 'met'
    assert {q.quote for q in result.evidence} == {'Прикладная информатика', 'Высшее образование окончено'}


def test_duplicate_alternative_preserves_quote_contexts():
    items = [{'alternative_key': 'a', 'status': 'confirmed', 'quote': 'Высшее', 'context_before': context}
             for context in ('Первое:', 'Второе:')]
    answer = keyed_formal({'a'}).model_validate({'alternatives': items}).alternatives[0]
    fragments = list(answer.quotes)
    if answer.quote:
        fragments.append(answer)
    assert {(q.quote, q.context_before) for q in fragments} == {('Высшее', 'Первое:'), ('Высшее', 'Второе:')}


def test_distinct_duplicate_indicator_evidence_requires_repair():
    with pytest.raises(ValidationError):
        keyed_competency({'i'}).model_validate({'indicators': [
            {'indicator_key': 'i', 'status': 'confirmed', 'quote': 'A'},
            {'indicator_key': 'i', 'status': 'confirmed', 'quote': 'B'},
        ]})


@pytest.mark.parametrize('payload', [
    {'alternatives': [{'alternative_key': 'PRIVATE_RESUME_MARKER', 'status': 'no_info'}]},
    {'PRIVATE_RESUME_MARKER': 'sensitive data'},
    {'alternatives': [{'alternative_key': 'a', 'status': 'PRIVATE_RESUME_MARKER'}]},
])
def test_validation_diagnostic_does_not_disclose_response(payload):
    raw = json.dumps(payload)
    llm = client(raw, raw, llm_structured_mode='prompt_json')
    with pytest.raises(LLMInvalidResponseError) as caught:
        call(llm, keyed_formal({'a'}))
    assert 'PRIVATE_RESUME_MARKER' not in str(caught.value)
    assert 'PRIVATE_RESUME_MARKER' not in str(llm.calls[0].as_audit())
    assert llm.calls[0].attempts == 2


def test_validation_diagnostic_keeps_schema_field_and_error_type():
    raw = json.dumps({'alternatives': [{'alternative_key': 'a', 'status': 'bad'}]})
    with pytest.raises(LLMInvalidResponseError) as caught:
        call(client(raw, raw), keyed_formal({'a'}))
    assert 'alternatives.0.status' in str(caught.value)
    assert 'literal_error' in str(caught.value)


@pytest.mark.parametrize('prompt,expected', [(ASSESS_PROMPT_VERSION, 'ready'), ('assess-v2', 'stale'), (None, 'stale')])
def test_api_detects_old_prompt_even_with_current_algorithm(prompt, expected):
    cid, pid, tid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assessment = SimpleNamespace(candidate_id=cid, profile_id=pid,
                                 algorithm_version=ALGORITHM_VERSION, prompt_version=prompt)
    rows = iter([[(cid, tid)], [(assessment, tid)]])
    session = SimpleNamespace(execute=lambda query: SimpleNamespace(all=lambda: next(rows)))
    state = resolve_states(session, [cid], SimpleNamespace(id=pid), uuid.uuid4(), False)[cid]
    assert state.status == expected
    if expected == 'stale':
        assert state.stale_reason == 'algorithm_changed'


def test_approval_command_does_not_create_unknown_hr():
    inserted = []
    session = SimpleNamespace(scalar=lambda query: None, add=inserted.append, flush=lambda: None)
    with pytest.raises(repo.RepositoryError):
        approver(session, 'missing-hr')
    assert inserted == []


@pytest.mark.parametrize('value,expected', [(None, 'no_info'), ('met', 'confirmed'), ('unknown', 'no_info')])
def test_merged_supported_status_aliases(value, expected):
    answer = keyed_formal({'a'}).model_validate({'alternatives': [{'alternative_key': 'a', 'status': value}]})
    assert answer.alternatives[0].status == expected
