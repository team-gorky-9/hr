"""Staff uploads use real PostgreSQL transactions and the real extraction/redaction pipeline."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import repository as repo
from app.db.enums import ApplicationSource
from app.db.models import Application, Candidate
from app.db.session import get_session
from app.main import create_app
from tests import factories as f
from tests.posting_helpers import posting_registry  # noqa: F401


@pytest.fixture
def client(session, posting_registry):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client


def params(session):
    return {"vacancy_id": str(f.vacancy(session).id), "filename": "resume.txt", "contour": "training"}


def test_upload_repeat_and_index_include_history(client, session):
    headers = {"X-User-Login": "hr_demo", "Content-Type": "application/octet-stream"}
    data = ("Python разработчик\nОпыт разработки программного обеспечения: Python, FastAPI, PostgreSQL. "
            "Разрабатывал API и автоматические тесты, сопровождал сервисы. " * 3).encode()
    first = client.post('/api/v1/candidates/upload', params=params(session), content=data, headers=headers)
    assert first.status_code == 201, first.text
    second = client.post('/api/v1/candidates/upload', params=params(session), content=data, headers=headers)
    assert second.status_code == 200, second.text
    assert first.json()['application_id'] == second.json()['application_id']
    candidate = session.get(Candidate, first.json()['candidate_id'])
    external = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.HISTORY,
                                       external_position_title='Внешняя должность')
    result = client.get('/api/v1/candidates', params={'q': candidate.code}, headers=headers)
    assert result.status_code == 200, result.text
    assert {str(external.id), first.json()['application_id']} <= {r['application_id'] for r in result.json()['items']}
    assert all(r['candidate_code'] == candidate.code for r in result.json()['items'])
    assert 'raw_text' not in result.text


def test_upload_rejects_scope_format_and_empty_file(client, session):
    url = '/api/v1/candidates/upload'
    headers = {'X-User-Login': 'dept_demo'}
    assert client.post(url, params=params(session), content=b'text', headers=headers).status_code == 403
    headers = {'X-User-Login': 'hr_demo'}
    assert client.post(url, params={**params(session), 'contour': 'working'}, content=b'text', headers=headers).status_code == 401
    assert client.post(url, params={**params(session), 'filename': 'bad.exe'}, content=b'text', headers=headers).status_code == 422
    assert client.post(url, params=params(session), content=b'', headers=headers).status_code == 422
    assert client.post(url, params={**params(session), 'filename': 'broken.docx'}, content=b'not a zip', headers=headers).status_code == 422
