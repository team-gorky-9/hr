"""Verify public loading on original documents; never commit or approve real profiles."""
import argparse
from collections import Counter
import json
from pathlib import Path

from sqlalchemy import select, text

from app.db.models import SourceDocument
from app.db.session import SessionLocal
from app.requirements import load_package
from app.requirements.cli import profile_summary
from app.requirements.package import read_json
from scripts.load_requirement_profiles import build_profile

ROOT = Path(__file__).resolve().parents[1]


def stored_fields(row, **kwargs):
    values = row.model_dump(mode='json', **kwargs)
    if 'acceptance' in values:
        # Repository omits null criteria in JSONB for both old and new loading paths.
        values['acceptance'] = row.acceptance.model_dump(exclude_none=True)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    fixture = ROOT / 'fixtures/requirement_profiles'
    package = read_json(fixture / 'profiles.draft.json')
    manifest = read_json(fixture / 'sources.json')
    synthetic = read_json(fixture / 'synthetic/cases.json')['synthetic_profile']
    with SessionLocal() as session:
        try:
            result = load_package(session, package, manifest, args.source_root,
                                  created_by='loader-verification', synthetic_profile=synthetic)
            documents = {item['id']: session.scalar(select(SourceDocument).where(
                SourceDocument.sha256 == item['sha256'])) for item in manifest['documents']}
            # Compare every stored row against the legacy mapper's validated schema.
            for spec, profile in zip([*package['profiles'], synthetic], result.profiles, strict=True):
                previous = build_profile(spec, documents, Counter())
                for expected, actual in zip(previous['formal_requirements'], profile.formal_requirements, strict=True):
                    for key, value in stored_fields(expected).items():
                        actual_value = getattr(actual, key)
                        assert getattr(actual_value, 'value', actual_value) == value, (expected.key, key)
                for expected, actual in zip(previous['competencies'], profile.competencies, strict=True):
                    for key, value in stored_fields(expected, exclude={'indicators'}).items():
                        actual_value = getattr(actual, key)
                        assert getattr(actual_value, 'value', actual_value) == value, (expected.key, key)
                    for indicator, stored in zip(expected.indicators, actual.indicators, strict=True):
                        for key, value in stored_fields(indicator).items():
                            actual_value = getattr(stored, key)
                            assert getattr(actual_value, 'value', actual_value) == value, (indicator.key, key)
                for expected, actual in zip(previous['sources'], profile.sources, strict=True):
                    for key, value in expected.model_dump().items():
                        assert getattr(actual, key) == value, ('source', key)
                assert [r.sort_order for r in profile.formal_requirements] == list(range(1, len(profile.formal_requirements) + 1))
                for competency in profile.competencies:
                    assert [r.sort_order for r in competency.indicators] == list(range(1, len(competency.indicators) + 1))
            assert [(len(p.formal_requirements), len(p.competencies), sum(len(c.indicators) for c in p.competencies))
                    for p in result.profiles] == [(2, 5, 54), (2, 8, 53), (1, 1, 1)]
            report = {'persisted': False, 'original_documents': len(documents),
                      'legacy_row_equivalence': True, 'profiles': [profile_summary(p) for p in result.profiles],
                      'review_fields': result.review_fields,
                      'postgresql': session.scalar(text('SHOW server_version')),
                      'pgvector': session.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))}
        finally:
            session.rollback()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
