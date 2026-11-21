from .conftest import PREFIX, headers, placement, post
from .test_3b import review, submission, task


def test_outcomes_package_and_withdrawal(client):
    p = placement(client)
    t = task(client, p["id"])
    s = submission(client, p["id"], t["id"])
    path = f"/placements/{p['id']}"
    completion = {"expected_revision": 1, "outcome": "completed", "reason": "Учебный итог"}
    assert post(client, path + "/complete", completion, "department", 409)["error"]["code"] == "REQUIRED_CRITERIA_UNCONFIRMED"
    review(client, s["id"])
    completed = post(client, path + "/complete", completion, "department")
    assert completed["completion"]["criteria_snapshot"][0]["result"] == "confirmed"
    assert client.get(PREFIX + path, headers=headers("candidate")).json()["university_result"]["result"] == "unknown"
    university = post(client, path + "/university-result", {"expected_revision": 2, "result": "passed",
        "source_reference": "Учебное письмо №1", "source_author": "Учебный координатор", "occurred_on": "2026-12-31"})
    assert university["completion"] == completed["completion"]
    package_body = {"criterion_keys": ["classification"], "purpose": "Ручное рассмотрение", "contact_basis": "Учебное основание контакта"}
    assert post(client, path + "/career-package", package_body, expected=409)["error"]["code"] == "CAREER_INTEREST_REQUIRED"
    post(client, path + "/career-interest", {"expected_revision": 3, "interested": True, "note": "Интересно"}, "candidate")
    package = post(client, path + "/career-package", package_body)
    assert package["education_status"] == "unconfirmed" and package["transfer_status"] == "prepared"
    assert len(package["selected_results"]) == 1 and package["university_result"]["result"] == "passed"
    package_path = PREFIX + f"/career-packages/{package['package_id']}"
    assert client.get(package_path, headers=headers("department")).status_code == 404
    assert client.get(package_path, headers=headers("candidate2")).status_code == 404
    assert client.get(package_path, headers=headers("hr_other")).status_code == 404
    post(client, path + "/career-interest", {"expected_revision": 4, "interested": False, "note": "Отзываю"}, "candidate")
    assert post(client, path + "/career-package", package_body, expected=409)["error"]["code"] == "CAREER_INTEREST_REQUIRED"
    old = client.get(package_path, headers=headers("candidate")).json()
    assert old["interest_withdrawn"] is True
    assert [h["action"] for h in old["history"]] == ["career_package_prepared", "interest_withdrawn"]
    assert old["selected_results"] == package["selected_results"]
    print({"placement": p["id"], "package": package["package_id"], "interest_withdrawn": old["interest_withdrawn"]})
