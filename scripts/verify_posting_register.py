"""Validate the fixed David review package, without DB, third-party packages or approvals."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'fixtures/posting_positions'


def read(name):
    return json.loads((PACKAGE / name).read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    register, evidence, coverage, examples = [read(name) for name in (
        'register.v1-draft.json', 'evidence.json', 'coverage.json', 'synthetic-cases.json')]
    rows = register['rows']
    require(register['status'] == 'proposal_for_consumer_review', 'Must remain a proposal')
    require(len(rows) == len({r['id'] for r in rows}) == 7, 'Expected seven distinct rows')
    require(len({unicodedata.normalize('NFC', r['posting_title']).casefold() for r in rows}) == 7,
            'Duplicate original title')
    counts = {r['posting_title']: r['document_count'] for r in rows}
    require(sum(counts.values()) == 242, 'Named publication counts')
    require(counts | {'(нет подвала)': 45} == coverage['postings'], 'Report and register differ')
    missing = register['missing_publication']
    require(missing['document_count'] == 45 and missing['with_external_history'] == 3
            and missing['without_history'] == 42 and missing['reason'] == 'missing_posting',
            'Unknown publication is a separate group')
    require(sum(counts.values()) + missing['document_count'] == coverage['application_records'] == 287,
            'Total document count')
    require(register['decision_coverage'] == {
        'confirmed_publications': 0, 'confirmed_documents': 0, 'no_matching_position_publications': 0,
        'needs_review_publications': 7, 'needs_review_named_documents': 242,
        'missing_publication_documents': 45}, 'Incorrect decision coverage')
    for row in rows:
        require(row['decision_state'] == 'needs_review', 'No HR decision has been received')
        require(all(row[key] is None for key in ('position_code', 'decision_author', 'decision_date', 'decision_basis')),
                'Do not invent a decision or approver')
        require(row['context']['dataset_sha256'] == coverage['archive_sha256'], 'Wrong dataset scope')
        require(row['context']['channel'] == 'hh_ru' and row['context']['employer_id'] is None,
                'Do not infer an employer from an imported folder')
        require(row['register_version'] == register['register_version'], 'Wrong row version')
        require(row['open_question'] and row['follow_up_owner'] == 'Давид'
                and row['decision_owner_role'] and row['observation'], 'Missing owner or question')
        require(row['source']['kind'] == 'docx_response_footer', 'Wrong source of publication')
        for ref in row['evidence_refs']:
            prefix, locator = ref.rsplit('/', 1)
            require(prefix == 'evidence.json#/paragraphs' and locator in evidence['paragraphs'],
                    'Broken evidence reference')
    policy_bytes = (ROOT / 'app/assessment/policies/hr-consultant.json').read_bytes()
    policy = json.loads(policy_bytes)
    policy_hash = hashlib.sha256(json.dumps(policy, ensure_ascii=False, sort_keys=True,
                                            separators=(',', ':')).encode('utf-8')).hexdigest()
    policy_counts = Counter()
    rules = {r['posting_title']: r for r in policy['rules']}
    for row in rows:
        expected = rules.get(row['posting_title'], {}).get('status', 'unresolved')
        require(row['current_policy'] == {'version': policy['version'], 'sha256': policy_hash,
                                         'position_code': 'hr-consultant', 'status': expected},
                'Policy observation drift')
        policy_counts[expected] += row['document_count']
    policy_counts['unresolved'] += 45
    require(dict(policy_counts) == {'unresolved': 266, 'mismatch': 21}, 'Policy coverage drift')
    require(coverage['counts'] == {'confirmed': 0, 'mismatch': 21, 'unresolved': 266}, 'Bad report totals')
    require(coverage['external_history_records'] == 24 and coverage['files_with_external_history'] == 4
            and coverage['history_record_distribution_per_file'] == [2, 2, 8, 12], 'History discrepancy lost')
    original = PACKAGE / evidence['path']
    require(hashlib.sha256(original.read_bytes()).hexdigest() == evidence['sha256'], 'Original DI changed')
    with zipfile.ZipFile(original) as archive:
        xml = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = {f'P{i}': ''.join(t.text or '' for t in p.findall('.//w:t', ns))
                  for i, p in enumerate(xml.findall('.//w:p', ns), 1)}
    for locator, quote in evidence['paragraphs'].items():
        require(quote == paragraphs[locator] and bool(quote.strip()), f'Quote differs at {locator}')
    require(examples['is_synthetic'] is True and len(examples['cases']) == 10, 'Synthetic cases missing')
    for decision in examples['example_decisions']:
        require(decision['decision_author'].startswith('synthetic-')
                and decision['decision_basis'].startswith('synthetic://'), 'Example mixed with real decisions')
        require((decision['position_code'] is not None) == (decision['decision_state'] == 'confirmed'),
                'Invalid example target')
    print(json.dumps({'result': 'passed', 'publication_rows': 7, 'named_documents': 242,
                      'missing_documents': 45, 'confirmed_real_mappings': 0,
                      'verified_source_quotes': len(evidence['paragraphs']), 'synthetic_scenarios': 10,
                      'application_integration_tested': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
