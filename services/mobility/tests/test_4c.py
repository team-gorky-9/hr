from .conftest import PREFIX, evidence, get, headers, post, selected, server
from .test_4b import agreed, proposal_body


def test_participation_result_and_separate_vacancy(database_url, actors_path):
    original_context = actors_path.read_bytes()
    with server(database_url, actors_path) as client:
        interest = selected(client)
        pending = post(client, f"/interests/{interest['id']}/proposal", proposal_body(), expected=201)
        post(client, f"/proposals/{pending['id']}/start", {"expected_revision": 1}, expected=409)
        post(client, f"/interests/{interest['id']}/withdraw", {"expected_revision": 2, "reason": "Период не подходит"}, "employee")
        assert get(client, f"/proposals/{pending['id']}")["status"] == "withdrawn"

        proposal = agreed(client)
        start_path = f"/proposals/{proposal['id']}/start"
        active = post(client, start_path, {"expected_revision": 3}, expected=201)
        repeated = post(client, start_path, {"expected_revision": 3}, expected=201)
        assert repeated["id"] == active["id"] and repeated["revision"] == 1
        assert active["proposal_revision"] == 3 and active["status"] == "active"
        path = f"/participations/{active['id']}"
        get(client, path, "other", 404)
        assert get(client, path, "manager")["status"] == "active"
        post(client, path + "/finish", {"expected_revision": 1, "outcome": "completed", "result_note": "Текст"}, "employee", 403)
        post(client, path + "/result-package", {"purpose": "Развитие", "share_allowed": True}, "employee", 409)
        response = client.patch(PREFIX + f"/proposals/{proposal['id']}", headers=headers("owner"),
            json={"expected_revision": 3, "time_percent": 25, "reason": "Новая доля"})
        assert response.status_code == 409
        post(client, f"/interests/{proposal['interest_id']}/withdraw", {"expected_revision": 2, "reason": "Отзыв после старта"}, "employee", 409)
        finished = post(client, path + "/finish", {"expected_revision": 1, "outcome": "completed",
                                                  "result_note": "Подготовлены программа и расписание практики"})
        feedback = post(client, path + "/employee-feedback", {"expected_revision": 2, "accepted": False,
                         "note": "Программа готова; расписание требует уточнения"}, "employee")
        assert feedback["owner_result"] == finished["owner_result"]
        package = post(client, path + "/result-package", {"purpose": "Развитие: планирование практики", "share_allowed": True}, "employee", 201)
        assert package["evidence"]["employee_feedback"]["accepted"] is False
        assert "manager_source_reference" not in package["evidence"] and "comment" not in package["evidence"]
        private_package = post(client, path + "/result-package", {"purpose": "Личная копия", "share_allowed": False}, "employee", 201)
        assert not private_package["share_allowed"] and private_package["delivery_status"] == "not_sent"
        assert "result_packages" not in get(client, path, "owner")

        vacancy = post(client, "/vacancy-interests", {"vacancy_ref": "fixture:internal-analyst-v1",
                       "publication_revision": 1, "comment": "Хочу обсудить постоянный переход"}, "employee", 201)
        vacancy_path = f"/vacancy-interests/{vacancy['id']}"
        assert vacancy["status"] == "prepared" and vacancy["consideration_ref"] is None
        get(client, vacancy_path, "manager", 404)
        get(client, vacancy_path, "foreign", 404)
        confirmation = {"expected_revision": 1, "consideration_ref": "fixture:recruitment-case-77",
                        "confirmation_basis": "HR вручную подтвердил учебное рассмотрение"}
        post(client, vacancy_path + "/record-consideration", confirmation, "owner", 403)
        registered = post(client, vacancy_path + "/record-consideration", confirmation, "hr")
        assert registered["status"] == "recorded" and registered["source_mode"] == "manual-confirmed"
        evidence(client, "c", {"active": active, "finished": finished, "feedback": feedback,
                               "result_package": package, "vacancy_prepared": vacancy, "vacancy_recorded": registered})
    with server(database_url, actors_path) as client:
        saved = get(client, path)
        assert saved["status"] == "completed" and saved["employee_feedback"]["accepted"] is False
        assert {p["id"] for p in saved["result_packages"]} == {package["id"], private_package["id"]}
        assert post(client, start_path, {"expected_revision": 3}, expected=201)["id"] == active["id"]
        assert get(client, vacancy_path)["consideration_ref"] == "fixture:recruitment-case-77"
    assert actors_path.read_bytes() == original_context  # No permanent assignment or transfer is written.
