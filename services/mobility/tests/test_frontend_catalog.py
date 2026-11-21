from tests.conftest import get, post, opportunity, EMPLOYEE, OWNER


def test_lists_do_not_expose_other_employees_interest(client):
    o = opportunity(client)
    i = post(client, f"/opportunities/{o['id']}/interests", {'comment': 'Private interest'}, 'employee', 201)
    assert get(client, '/interests')['items'][0]['id'] == i['id']
    assert get(client, '/interests', 'owner')['items'][0]['id'] == i['id']
    assert get(client, '/interests', 'other')['items'] == []
    assert get(client, '/interests', 'foreign')['items'] == []
    colleagues = get(client, '/colleagues')['items']
    assert all(set(p) == {'actor_id', 'login', 'roles'} for p in colleagues)
    assert all(p['login'] != 'foreign' for p in colleagues)
    assert all(a['employee_actor_id'] == EMPLOYEE for a in get(client, '/manager-assignments')['items'])
    assert get(client, '/proposals')['items'] == []
    assert get(client, '/participations')['items'] == []
    v = post(client, '/vacancy-interests', {'vacancy_ref': 'requirements:published-test', 'publication_revision': 2}, 'employee', 201)
    assert get(client, '/vacancy-interests')['items'][0]['id'] == v['id']
    assert get(client, '/vacancy-interests', 'hr')['items'][0]['id'] == v['id']
    assert get(client, '/vacancy-interests', 'other')['items'] == []
