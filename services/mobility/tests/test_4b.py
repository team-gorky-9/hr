import json

from .conftest import (EMPLOYEE, MANAGER, MANAGER2, PREFIX, SOURCE, evidence,
                       get, headers, post, selected, server)


def proposal_body(manager=MANAGER, source=SOURCE):
    return dict(starts_on="2026-12-01", ends_on="2026-12-31", time_percent=20,
                manager_actor_id=manager, manager_source_reference=source)


def agreed(client):
    interest = selected(client)
    row = post(client, f"/interests/{interest['id']}/proposal", proposal_body(), expected=201)
    post(client, f"/proposals/{row['id']}/employee-response", {"expected_revision": 1, "accepted": True}, "employee")
    return post(client, f"/proposals/{row['id']}/manager-response", {"expected_revision": 2, "accepted": True}, "manager")


def test_time_versions_and_reassignment(database_url, actors_path):
    with server(database_url, actors_path) as client:
        interest = selected(client)
        url = f"/interests/{interest['id']}/proposal"
        post(client, url, proposal_body(EMPLOYEE), expected=422)
        post(client, url, proposal_body(source="unconfirmed"), expected=422)
        row = post(client, url, proposal_body(), expected=201)
        path = f"/proposals/{row['id']}"
        get(client, path, "manager", 404)
        get(client, path, "other", 404)
        employee = post(client, path + "/employee-response", {"expected_revision": 1, "accepted": True}, "employee")
        assert employee["status"] == "awaiting_manager"
        assert len(get(client, path, "manager")["history"]) == 1
        post(client, path + "/manager-response", {"expected_revision": 2, "accepted": False}, "manager", 422)
        declined = post(client, path + "/manager-response", {"expected_revision": 2, "accepted": False,
                        "reason": "Отчётный период, прошу начало позже"}, "manager")
        response = client.patch(PREFIX + path, headers=headers("owner"), json={
            "expected_revision": 3, "starts_on": "2026-12-15", "reason": "Период уточнён"})
        assert response.status_code == 200, response.text
        revised = response.json()
        assert revised["status"] == "awaiting_employee"
        assert revised["employee_response"] is revised["manager_response"] is None
        get(client, path, "manager", 404)
        post(client, path + "/manager-response", {"expected_revision": 2, "accepted": True}, "manager", 409)
        post(client, path + "/employee-response", {"expected_revision": 4, "accepted": True}, "employee")
        approved = post(client, path + "/manager-response", {"expected_revision": 5, "accepted": True}, "manager")
        assert approved["status"] == "agreed" and approved["starts_on"] == "2026-12-15"
        assert approved["employee_response_record"]["conditions_revision"] == approved["manager_response_record"]["conditions_revision"] == 2

        # Simulate the authoritative fixture changing, not a client assigning itself rights.
        context = json.loads(actors_path.read_text())
        old = context["manager_assignments"][0]
        old["active"] = False
        context["manager_assignments"].append({**old, "manager_actor_id": MANAGER2,
                                              "source_reference": "fixture:reassigned-v2", "active": True})
        actors_path.write_text(json.dumps(context), encoding="utf-8")
        get(client, path, "manager", 404)
        replacement = post(client, url, proposal_body(MANAGER2, "fixture:reassigned-v2"), expected=201)
        assert replacement["id"] != row["id"] and replacement["employee_response"] is None
        assert get(client, path)["status"] == "withdrawn"
        post(client, path + "/manager-response", {"expected_revision": 6, "accepted": True}, "manager", 404)
        new_path = f"/proposals/{replacement['id']}"
        get(client, new_path, "manager2", 404)
        post(client, new_path + "/employee-response", {"expected_revision": 1, "accepted": True}, "employee")
        final = post(client, new_path + "/manager-response", {"expected_revision": 2, "accepted": True}, "manager2")
        assert final["status"] == "agreed"
        another = selected(client)
        refusal = post(client, f"/interests/{another['id']}/proposal", proposal_body(MANAGER2, "fixture:reassigned-v2"), expected=201)
        refusal = post(client, f"/proposals/{refusal['id']}/employee-response", {"expected_revision": 1, "accepted": False}, "employee")
        assert refusal["status"] == "declined" and refusal["reason"] is None
        get(client, f"/proposals/{refusal['id']}", "manager2", 404)
        evidence(client, "b", {"declined": declined, "revised": revised, "agreed": approved,
                               "reassigned": final, "history": get(client, path)})
    with server(database_url, actors_path) as client:
        saved = get(client, new_path)
        assert saved["status"] == "agreed" and saved["manager_actor_id"] == MANAGER2
        assert get(client, path)["superseded_by"] == saved["id"]
