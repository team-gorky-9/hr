"""One replayable synthetic HTTP demonstration, including a real process restart."""
import json
import os
from pathlib import Path

from .conftest import PREFIX, apply, headers, opportunity, post, server
from .test_3b import review, submission, task


def test_practice_demo(database_url):
    trace = []

    def capture(response):
        response.read()
        request = response.request
        if not request.url.path.startswith(PREFIX):
            return
        trace.append({
            "actor": request.headers["authorization"].removeprefix("Bearer fixture:"),
            "method": request.method, "path": request.url.path,
            "request": json.loads(request.content) if request.content else None,
            "status": response.status_code, "response": response.json(),
        })

    def read(client, path, login="candidate", expected=200):
        response = client.get(PREFIX + path, headers=headers(login))
        assert response.status_code == expected, response.text
        return response.json()

    with server(database_url) as client:
        client.event_hooks["response"].append(capture)
        opening = opportunity(client)
        first = apply(client, opening["id"])
        second = apply(client, opening["id"], "candidate2")
        placement = post(client, f"/applications/{first['id']}/assign", {
            "expected_revision": first["revision"],
            "confirmation_basis": "synthetic: HR manually checked training dates and mentor",
        })
        blocked = post(client, f"/applications/{second['id']}/assign", {
            "expected_revision": second["revision"], "confirmation_basis": "synthetic: second applicant",
        }, expected=409)
        assert blocked["error"]["code"] == "CAPACITY_UNAVAILABLE"
        assert read(client, f"/applications/{second['id']}", "candidate2")["status"] == "submitted"
        path = f"/placements/{placement['id']}"
        assignment = task(client, placement["id"])
        initial = submission(client, placement["id"], assignment["id"], "Учебная классификация без объяснения спорной категории")
        returned = review(client, initial["id"], "needs_revision")
        assert read(client, path + "/submissions")["work_state"] == "needs_revision"
        corrected = submission(client, placement["id"], assignment["id"], "Учебное исправление: категория выбрана по предмету обращения; основание объяснено")
        accepted = review(client, corrected["id"])
        saved_work = read(client, path + "/submissions")
        assert saved_work["work_state"] == "confirmed" and len(saved_work["items"]) == 2
        assert saved_work["items"][0]["review"]["id"] == returned["id"]
        read(client, path + "/submissions", "candidate2", 404)
        placement = post(client, path + "/complete", {
            "expected_revision": placement["revision"], "outcome": "completed",
            "reason": "Учебный итог принимающей стороны: исправленная работа подтверждена",
        }, "department")
        assert read(client, path)["university_result"]["result"] == "unknown"
        host_result = placement["completion"]
        placement = post(client, path + "/university-result", {
            "expected_revision": placement["revision"], "result": "passed",
            "source_reference": "synthetic: university letter DEMO-6A dated 2026-12-31",
            "source_author": "Учебный координатор вуза (внешний автор)", "occurred_on": "2026-12-31",
        })
        assert placement["completion"] == host_result
        placement = post(client, path + "/career-interest", {
            "expected_revision": placement["revision"], "interested": True,
            "note": "Учебное согласие обсудить работу после выпуска",
        }, "candidate")
        package = post(client, path + "/career-package", {
            "criterion_keys": ["classification"], "purpose": "Учебное ручное рассмотрение после выпуска",
            "contact_basis": "synthetic: expressed career interest in this placement",
        })
        assert package["transfer_status"] == "prepared" and package["education_status"] == "unconfirmed"
        assert package["selected_results"][0]["submission_id"] == corrected["id"]
        assert package["selected_results"][0]["review_id"] == accepted["id"]
        package_path = f"/career-packages/{package['package_id']}"
        read(client, package_path, "candidate2", 404)
        before_restart = read(client, package_path)

    # A second uvicorn process opens the same SQLite database.
    with server(database_url) as client:
        client.event_hooks["response"].append(capture)
        saved = read(client, path)
        assert saved["status"] == "completed" and saved["completion"] == host_result
        assert saved["university_result"]["result"] == "passed"
        assert read(client, path + "/submissions") == saved_work
        assert read(client, package_path) == before_restart
        read(client, package_path, "candidate2", 404)

    ids = {"opportunity": opening["id"], "application": first["id"], "second_application": second["id"],
           "placement": placement["id"], "task": assignment["id"], "first_submission": initial["id"],
           "corrected_submission": corrected["id"], "package": package["package_id"]}
    report_dir = os.environ.get("WAVE6_REPORT_DIR")
    if report_dir:
        target = Path(report_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "wave-6-practice-examples.json").write_text(json.dumps({
            "is_synthetic": True, "source": "practice-training-wave6-v1", "ids": ids,
            "restart_verified": True, "archive_receipt": None, "trace": trace,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(ids, ensure_ascii=False))
