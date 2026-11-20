"""Explicit decision evidence for service integration tests; never production defaults."""
from app.db import repository as repo
from app.db.models import ApplicationPostingSource
from app.postings.registry import Registry, PostingRule, RegistryContext
from tests import factories as f

CONTEXT = RegistryContext(dataset_id='test-package', dataset_sha256='a'*64,
    channel='hh_ru', source_folder='Test', is_synthetic=False)

def registry(*, context=CONTEXT, state='confirmed', target='python-dev', version='test-v1', title='Publication'):
    terminal = state != 'needs_review'
    return Registry(schema_version='posting-register/1.0', version=version, rules=[PostingRule(
        id='test-decision', context=context, match_kind='posting_title', posting_title=title,
        decision_state=state, position_code=target if state == 'confirmed' else None,
        decision_author='test-owner' if terminal else None,
        decision_date='2026-11-20' if terminal else None,
        decision_basis='Synthetic integration evidence' if terminal else None,
        evidence_refs=['test-only'] if terminal else [], reason=state)])

def response(session, candidate, *, imported='hr-consultant', title='Publication', context=CONTEXT):
    app = repo.create_application(session, candidate_id=candidate.id, source='response',
        vacancy_id=f.vacancy(session, imported).id, posting_title=title)
    session.add(ApplicationPostingSource(application_id=app.id, dataset_id=context.dataset_id,
        dataset_sha256=context.dataset_sha256, channel=context.channel, source_folder=context.source_folder,
        source_path='Test/resume.txt', source_sha256='b'*64))
    session.flush()
    return app
