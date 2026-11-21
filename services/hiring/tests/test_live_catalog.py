"""Exact identity, current closure, and unavailable authority; no title matching."""
import uuid
import httpx
import pytest
from hiring.config import Settings
from hiring import portal
from hiring.schemas import PortalVacancyRef
from hiring.errors import Problem
ORG = uuid.UUID('00000000-0000-4000-8000-000000000001')
ID = '00000000-0000-4000-8000-000000000c01'
REF = PortalVacancyRef(system='requirements', id=ID, revision=2)
ROW = {'id': ID, 'organization_id': str(ORG), 'revision': 2, 'title': 'Actual vacancy', 'position_code': 'economist', 'status': 'published'}

def test_exact_ref_and_closure(monkeypatch):
    settings = Settings(requirements_url='http://requirements:8000')
    current = dict(ROW)
    monkeypatch.setattr(portal, 'requirements_get', lambda settings, path: dict(current))
    snapshot, question = portal.resolve_vacancy(settings, ORG, REF)
    assert question is None and snapshot['source'] == 'requirements'
    current['status'] = 'closed'
    assert portal.resolve_vacancy(settings, ORG, REF)[1] == 'vacancy_closed'
    assert portal.resolve_vacancy(settings, uuid.uuid4(), REF) == (None, 'vacancy_unknown')
    assert portal.resolve_vacancy(settings, ORG, REF.model_copy(update={'revision': 1})) == (None, 'vacancy_unknown')

def test_catalog_outage_is_retryable_not_unknown(monkeypatch):
    settings = Settings(requirements_url='http://requirements:8000')
    def unavailable(*args, **kwargs):
        raise httpx.ReadTimeout('offline')
    monkeypatch.setattr(portal.httpx, 'get', unavailable)
    with pytest.raises(Problem) as exc:
        portal.resolve_vacancy(settings, ORG, REF)
    assert exc.value.status == 503 and exc.value.code == 'CATALOG_UNAVAILABLE'

def test_fixture_reference_remains_resolvable_when_live_enabled():
    settings = Settings(requirements_url='http://requirements:8000')
    snapshot, question = portal.resolve_vacancy(settings, ORG, PortalVacancyRef(system='catalog', id=ID, revision=1))
    assert snapshot['source'] == 'training_snapshot' and question is None
