"""Read-only archive coverage, no LLM, no candidate rejection or DB writes.

python -m scripts.report_profile_applicability ARCHIVE.zip --output report.json
Report contains file hashes and posting titles, never resume text or personal data.
Counts are application records, not deduplicated people and not model accuracy.
"""
import argparse
import hashlib
import json
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from app.assessment.applicability import Policy, DEFAULT_POLICY, digest, resolve_applicability
from app.db.seed import POSITION_CODE_BY_FOLDER
from app.ingest.extract import extract_text
from app.ingest.history import parse_history
from app.ingest.package import RESUME_NAME


def summarize(rows, policy=None):
    policy = policy or Policy.model_validate_json(DEFAULT_POLICY.read_text(encoding='utf-8'))
    counts = dict(confirmed=0, mismatch=0, unresolved=0)
    reasons = Counter()
    titles = Counter()
    for row in rows:
        mapping = resolve_applicability('hr-consultant', row['posting_title'], policy=policy)
        counts[mapping.status] += 1
        reasons[mapping.reason] += 1
        titles[row['posting_title'] or '(нет подвала)'] += 1
    return dict(application_records=len(rows), counts=counts, reason_counts=dict(reasons),
                eligible_primary_records=counts['confirmed'],
                missing_posting_records=reasons.get('missing_posting', 0),
                external_history_records=sum(row['external_history_count'] for row in rows),
                files_with_external_history=sum(row['external_history_count'] > 0 for row in rows),
                postings=dict(sorted(titles.items())), policy_version=policy.version,
                policy_hash=digest(policy.model_dump()))


def report_archive(path):
    folders = {unicodedata.normalize('NFC', k).casefold(): v for k, v in POSITION_CODE_BY_FOLDER.items()}
    rows = []
    with zipfile.ZipFile(path, metadata_encoding='utf-8') as archive:
        for member in archive.infolist():
            name = PurePosixPath(unicodedata.normalize('NFC', member.filename.replace('\\', '/')))
            if member.is_dir() or not RESUME_NAME.fullmatch(name.name):
                continue
            if not any(folders.get(part.casefold()) == 'hr-consultant' for part in name.parts[:-1]):
                continue
            content = archive.read(member)
            history = parse_history(extract_text(content, name.suffix))
            rows.append(dict(source_sha256=hashlib.sha256(content).hexdigest(),
                             posting_title=history.response_title, external_history_count=len(history.external)))
    result = summarize(rows)
    result.update(archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  scope='hr-consultant response files; records, not unique people',
                  model_calls=0, assessment_created=False, records=rows)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = report_archive(args.archive)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, ensure_ascii=False, indent=2))
    return 0 if result['application_records'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
