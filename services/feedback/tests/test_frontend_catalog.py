from fastapi.testclient import TestClient
from feedback.api import create_app
from feedback.store import seed_demo
from tests.test_cycle import call, cycle_body


def test_cycle_directory_is_scoped_and_does_not_disclose_codes(tmp_path):
    database = tmp_path / 'feedback.db'
    seed_demo(database)
    with TestClient(create_app(database)) as client:
        c = call(client, 'POST', '/cycles', body=cycle_body(), status=201)
        assert call(client, 'GET', '/cycles', 'alice')['items'] == []
        assert call(client, 'GET', '/cycles')['items'][0]['id'] == c['id']
        call(client, 'POST', f"/cycles/{c['id']}/open", body={'expected_revision': 1})
        codes = call(client, 'POST', f"/cycles/{c['id']}/access-codes", body={'group_key': 'large', 'count': 1})
        employee = call(client, 'GET', '/cycles', 'alice')['items'][0]
        assert set(employee) == {'id', 'title', 'status', 'revision', 'question_version'}
        assert codes['codes'][0] not in str(employee)
        assert call(client, 'GET', '/cycles', 'outsider')['items'] == []
        assert 'token_hash' not in call(client, 'GET', '/session', 'alice')
