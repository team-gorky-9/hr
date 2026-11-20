"""Addressed replay of 41 independent formal-rule cases, controlled or live.

No DB writes or operational recommendations. Live mode measures formal extraction,
not CandidateCard extraction or complete profile quality. Expected outputs never
enter the live prompt. Unsupported rules must stop before any model call.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from app.ai import LLMError, build_client
from app.ai.fake import FakeLLMClient
from app.assessment.errors import RuleUnsupportedError
from app.assessment.rules import parse_rule
from app.assessment.service import _assess_formal
from app.assessment.version import ALGORITHM_VERSION
from app.assessment.prompts import ASSESS_PROMPT_VERSION
from scripts.profile_case_inputs import CASES, ROOT, case_profile, controlled_reply


def replay(mode, limit=None):
    live = build_client() if mode == 'live' else None
    results = []
    cases = CASES[:limit] if limit else CASES
    for number, case in enumerate(cases, 1):
        started = time.monotonic()
        profile, text = case_profile(case)
        llm = live or FakeLLMClient(lambda *args: controlled_reply(case, profile))
        before = len(llm.calls)
        expected = case['expected']['result']
        outcome = dict(case_id=case['id'], rule_key=case['rule_key'], expected=expected)
        try:
            rules = {r.key: parse_rule(r.key, r.kind, r.params, r.verification) for r in profile.formal_requirements}
            drafts = _assess_formal(profile, rules, text, llm, ASSESS_PROMPT_VERSION, case.get('as_of', '2026-11'))
            target = next(d for d in drafts if d.requirement.key == case['rule_key'])
            outcome.update(actual=target.result.value, passed=target.result == expected,
                alternatives=[a.model_dump(mode='json') for a in target.alternatives],
                details=target.details, evidence=[e.model_dump(mode='json') for e in target.evidence])
        except RuleUnsupportedError:
            outcome.update(actual='processing_error', passed=expected == 'processing_error' and len(llm.calls) == before)
        except LLMError as error:
            # Сбой модели в одном случае не останавливает прогон: случай не пройден, причина в отчёте.
            outcome.update(actual='llm_error', passed=False, error=str(error))
        outcome['model_calls'] = len(llm.calls) - before
        # Ход прогона — в stderr, чтобы было видно, что живой режим не завис (≈3–10 с на случай).
        print(f"[{number}/{len(cases)}] {case['id']}: {outcome.get('actual')} "
              f"(ожидалось {expected}, {time.monotonic() - started:.1f} с)", file=sys.stderr, flush=True)
        results.append(outcome)
    return dict(mode=mode, algorithm_version=ALGORITHM_VERSION, prompt_version=ASSESS_PROMPT_VERSION,
        fixture_sha256=hashlib.sha256((ROOT / 'synthetic/cases.json').read_bytes()).hexdigest(),
        total=len(results), passed=sum(r['passed'] for r in results),
        llm_errors=sum(r['actual'] == 'llm_error' for r in results),
        scope='target rule only; controlled is not model-quality evidence; no database writes', results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['controlled', 'live'], default='controlled')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, help='только первые N случаев (быстрая проверка живого режима)')
    args = parser.parse_args()
    result = replay(args.mode, args.limit)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'results'}, ensure_ascii=False))
    return 0 if result['passed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
