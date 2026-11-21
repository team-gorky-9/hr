from .conftest import evidence, get, opportunity, post, server


def test_interest_visibility_withdrawal_and_persistence(database_url, actors_path):
    with server(database_url, actors_path) as client:
        first = opportunity(client)
        second = opportunity(client, "Учебная аналитическая задача")
        assert len(get(client, "/opportunities")["items"]) == 2
        assert get(client, f"/opportunities/{second['id']}")["status"] == "open"
        interest = post(client, f"/opportunities/{first['id']}/interests", {"comment": "Мой учебный интерес"}, "employee", 201)
        duplicate = post(client, f"/opportunities/{first['id']}/interests", {"comment": "Повтор"}, "employee", 201)
        assert duplicate["id"] == interest["id"] and duplicate["revision"] == 1
        path = f"/interests/{interest['id']}"
        get(client, path, "manager", 404)
        get(client, path, "foreign", 404)
        assert get(client, f"/opportunities/{first['id']}/interests", "manager")["items"] == []
        assert len(get(client, f"/opportunities/{first['id']}/interests", "owner")["items"]) == 1
        chosen = post(client, path + "/select", {"expected_revision": 1})
        assert chosen["status"] == "selected"
        withdrawn = post(client, path + "/withdraw", {"expected_revision": 2, "reason": "Не подходит период"}, "employee")
        assert withdrawn["status"] == "withdrawn"
        post(client, path + "/select", {"expected_revision": 1}, expected=409)
        renewed = post(client, f"/opportunities/{first['id']}/interests", {}, "employee", 201)
        declined = post(client, f"/interests/{renewed['id']}/decline", {"expected_revision": 1, "reason": "Выбран другой участник"})
        assert declined["status"] == "not_selected"
        evidence(client, "a", {"opportunity": first, "selected": chosen, "withdrawn": withdrawn, "declined": declined})
    with server(database_url, actors_path) as client:
        saved = get(client, path)
        assert saved["reason"] == "Не подходит период"
        assert [h["action"] for h in saved["history"]] == ["submitted", "selected", "withdrawn"]
