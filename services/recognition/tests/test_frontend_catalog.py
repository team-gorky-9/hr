from fastapi.testclient import TestClient
from recognition.api import create_app
from recognition.store import seed_demo, DEMO_IDS
from tests.test_thanks import call


def test_employee_directory_and_moderation_visibility(tmp_path):
    database = tmp_path / 'recognition.db'
    seed_demo(database)
    with TestClient(create_app(database)) as client:
        peers = call(client, 'GET', '/colleagues', 'alice')['items']
        assert all(set(p) == {'id', 'name'} for p in peers)
        assert DEMO_IDS['outsider'] not in {p['id'] for p in peers}
        t = call(client, 'POST', '/thanks', 'alice', {'recipient_id': DEMO_IDS['bob'], 'text': 'Help', 'requested_visibility': 'organization'}, 201)
        assert call(client, 'GET', '/thanks?view=moderation', 'moderator')['items'] == []
        call(client, 'POST', f"/thanks/{t['id']}/visibility", 'bob', {'expected_revision': 1, 'choice': 'organization'})
        assert call(client, 'GET', '/thanks?view=moderation', 'moderator')['items'][0]['id'] == t['id']
        assert call(client, 'GET', '/thanks?view=moderation', 'reader')['items'] == []
        assert 'token_hash' not in call(client, 'GET', '/session', 'alice')
