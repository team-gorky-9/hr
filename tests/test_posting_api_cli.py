import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.db.models import Application
from app.main import create_app
from app.postings import service
from tests import factories as f
from tests.posting_service_helpers import registry, response

@pytest.fixture
def case(session, monkeypatch):
    candidate = f.make_candidate(session, 'posting-http')
    application = response(session, candidate)
    f.approve(session, f.make_profile(session, 'python-dev'))
    monkeypatch.setattr(service, 'get_default_registry', lambda: registry())
    return candidate, application

@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client

def test_snapshot_http_auth_frozen_read_and_no_application_mutations(session, client, case, monkeypatch):
    _, application = case
    path = f'/api/v1/applications/{application.id}/posting-resolution'
    assert client.get(path).json()['position_code'] == 'python-dev'
    assert client.get(f'/api/v1/applications/{uuid.uuid4()}/posting-resolution').status_code == 404
    body = {'application_ids': [str(application.id)]}
    assert client.post('/api/v1/posting-snapshots', json=body).status_code == 401
    assert client.post('/api/v1/posting-snapshots', json=body,
        headers={'X-User-Login':'dept_demo'}).status_code == 403
    headers = {'X-User-Login': 'hr_demo'}
    count = session.scalar(select(func.count()).select_from(Application))
    saved = client.post('/api/v1/posting-snapshots', json=body, headers=headers)
    assert saved.status_code == 201, saved.text
    snapshot = saved.json()
    monkeypatch.setattr(service, 'get_default_registry', lambda: registry(state='needs_review', version='test-v2'))
    assert client.get(path).json()['ready'] is False
    read = client.get(f"/api/v1/posting-snapshots/{snapshot['snapshot_id']}", headers=headers)
    assert read.status_code == 200 and read.json() == snapshot
    assert session.scalar(select(func.count()).select_from(Application)) == count
    assert application.current_stage_code == 'new'
    assert 'source_path"' not in read.text and 'raw_text' not in read.text
    assert client.get(f'/api/v1/posting-snapshots/{uuid.uuid4()}', headers=headers).status_code == 404
    assert client.post('/api/v1/posting-snapshots',json={'application_ids':[str(uuid.uuid4())]},headers=headers).status_code == 422

def test_cli_primary_needs_no_profile_or_position(session, monkeypatch, capsys, case):
    from app.assessment import __main__ as cli
    from app.db import session as db_session
    from app.ai.fake import FakeLLMClient
    candidate, application = case
    connection = session.connection()
    monkeypatch.setattr(db_session, 'SessionLocal', lambda: Session(bind=connection, join_transaction_mode='create_savepoint'))
    monkeypatch.setattr(cli, '_DeferredClient', lambda: FakeLLMClient(lambda *args: {}))
    assert cli.main(['run','--candidate-code',candidate.code,'--application-id',str(application.id)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['position_code'] == 'python-dev' and payload['status'] == 'ok'
    assert payload['registry_snapshot']['version'] == 'test-v1'

def test_snapshot_cli_uses_stored_version_on_read(session, monkeypatch, capsys, case, tmp_path):
    from app.postings import __main__ as cli
    from app.db import session as db_session
    _, application = case
    (tmp_path/'versions').mkdir()
    (tmp_path/'versions/test-v1.json').write_text(registry().model_dump_json(),encoding='utf-8')
    (tmp_path/'current.json').write_text('{"version":"test-v1"}',encoding='utf-8')
    connection = session.connection()
    monkeypatch.setattr(db_session,'SessionLocal',lambda: Session(bind=connection,join_transaction_mode='create_savepoint'))
    assert cli.main(['--registry-dir',str(tmp_path),'snapshot','--application-id',str(application.id)]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    (tmp_path/'current.json').write_text('{"version":"absent"}',encoding='utf-8')
    assert cli.main(['--registry-dir',str(tmp_path),'read-snapshot','--snapshot-id',snapshot['snapshot_id']]) == 0
    assert json.loads(capsys.readouterr().out) == snapshot
