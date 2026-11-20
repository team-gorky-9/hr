"""The acceptance example of the card on Marina's training case, step by step through HTTP."""
from tests.conftest import (
    CANDIDATE,
    basis_document,
    create_case,
    current,
    item,
    pdf,
    ready_case,
    review,
    started_case,
    submit,
)

EMPLOYEE = "00000000-0000-4000-8000-000000000201"
ASSIGNMENT = "00000000-0000-4000-8000-000000000302"


def record(api, case, actual="2026-11-23", system="workforce", basis="Назначение зарегистрировано"):
    return api.post("hr", f"/cases/{case['id']}/record-assignment", {
        "expected_revision": current(api, case)["revision"],
        "employee_ref": {"system": system, "id": EMPLOYEE},
        "assignment_ref": {"system": system, "id": ASSIGNMENT},
        "actual_starts_on": actual, "confirmation_basis": basis})


def test_health_declares_stage_one(api):
    body = api.client.get("/health").json()
    assert body["status"] == "ok" and body["implementation_stage"] == 1
    assert (body["integration_mode"], body["auth_mode"], body["transfer_mode"]) == ("standalone", "fixture", "manual")
    assert api.client.get("/ready").json() == {"status": "ok", "database": "ok", "broker": "not_used"}


def test_full_training_path(api, marina):
    # 1. Case from selection.json with a checklist; the candidate login opens only the linked case.
    case = create_case(api, marina)
    assert (case["status"], case["revision"], case["workforce_status"]) == ("preparing", 1, "not_sent")
    assert case["provenance"]["source_mode"] == "fixture" and case["is_synthetic"] is True
    assert [c["id"] for c in api.get("candidate", "/cases").json()["items"]] == [case["id"]]

    requested = api.post("hr", f"/cases/{case['id']}/request-documents",
                         {"expected_revision": case["revision"], "message": "Загрузите документы"})
    assert requested.json()["status"] == "awaiting_documents"

    # 2. Two files, one returned with a reason; ready is refused until all required items are accepted.
    submit(api, case, "passport")
    first = submit(api, case, "education")
    review(api, case, "passport")
    returned = review(api, case, "education", "needs_revision", "Скан нечитаем")
    assert returned["status"] == "needs_revision"
    refused = api.post("hr", f"/cases/{case['id']}/ready", {"expected_revision": current(api, case)["revision"]})
    assert refused.status_code == 409 and refused.json()["error"] == {
        "code": "INVALID_STATE", "message": "Required items are not accepted: education", "field": "checklist",
        "request_id": refused.json()["error"]["request_id"]}

    seen = api.get("candidate", f"/cases/{case['id']}").json()
    assert item(seen, "education")["review_reason"] == "Скан нечитаем"
    second = submit(api, case, "education")
    assert second["document_ids"][0] == first["document_ids"][0] and len(second["document_ids"]) == 2
    review(api, case, "education")
    ready = api.post("hr", f"/cases/{case['id']}/ready", {"expected_revision": current(api, case)["revision"]})
    assert ready.json()["status"] == "ready"

    # 3. Start with a basis document; nothing waits for Workforce in stage 1.
    order = basis_document(api)
    started = api.post("hr", f"/cases/{case['id']}/start", {
        "expected_revision": ready.json()["revision"], "starts_on": "2026-11-23",
        "basis": {"document_id": order["id"], "reference": "DEMO-21", "issued_on": "2026-11-21"},
        "confirmation_basis": "Оригиналы сверены"}).json()
    assert (started["status"], started["workforce_status"], started["transfer_mode"]) == ("started", "not_sent", "manual")
    assert started["employee_id"] is None and started["workforce_confirmation"] is None

    data = api.get("hr", f"/cases/{case['id']}/registration-data").json()
    assert data == {
        "case_id": case["id"], "case_revision": started["revision"], "application_ref": marina["application_ref"],
        "person_ref": marina["candidate_ref"], "organization_id": marina["organization_id"],
        "department_id": marina["department_id"], "position_code": "economist-training", "starts_on": "2026-11-23",
        "basis": {"document_ref": {"service": "hiring", "id": order["id"]}, "reference": "DEMO-21",
                  "issued_on": "2026-11-21"},
        "transfer_mode": "manual"}

    # After the HR confirmation the employee and assignment references appear.
    registered = record(api, case).json()
    assert registered["workforce_status"] == "registered" and registered["status"] == "started"
    assert (registered["employee_id"], registered["assignment_id"]) == (EMPLOYEE, ASSIGNMENT)
    confirmation = registered["workforce_confirmation"]
    assert confirmation["recorded_by_actor_id"] == "00000000-0000-4000-8000-000000000101"
    assert confirmation["actual_starts_on"] == registered["workforce_assignment_snapshot"]["starts_on"] == "2026-11-23"
    assert registered["workforce_assignment_snapshot"]["source"] == {"system": "workforce", "method": "manual-confirmed"}

    history = [e["event_type"] for e in api.get("hr", f"/cases/{case['id']}/history").json()["items"]]
    assert history == ["case.created", "documents.requested", "item.submitted", "item.submitted", "item.reviewed",
                       "item.reviewed", "item.submitted", "item.reviewed", "case.ready", "case.started",
                       "assignment.recorded"]


def test_candidate_view_hides_internal_fields(api, marina):
    case = started_case(api, marina)
    view = api.get("candidate", f"/cases/{case['id']}").json()
    assert "selection" not in view and "basis" not in view and "candidate_actor_id" not in view
    assert all("reviewed_by_actor_id" not in entry for entry in view["checklist"])
    assert view["starts_on"] == "2026-11-23" and view["status"] == "started"
    record_response = api.post("hr", f"/cases/{case['id']}/link-account", {
        "expected_revision": case["revision"], "candidate_actor_id": CANDIDATE, "identity_basis": "повтор"})
    assert record_response.status_code == 200
    events = api.get("candidate", f"/cases/{case['id']}/history").json()["items"]
    assert all("actor_id" not in e for e in events)
    types = [e["event_type"] for e in events]
    assert "account.linked" not in types and "case.started" in types
    started_event = next(e for e in events if e["event_type"] == "case.started")
    assert started_event["data"] == {"starts_on": "2026-11-23"}


def test_new_file_revokes_accepted_version_and_readiness(api, marina):
    case = ready_case(api, marina)
    accepted = item(current(api, case), "passport")
    resubmitted = submit(api, case, "passport")
    after = current(api, case)
    assert resubmitted["status"] == "received" and after["status"] == "awaiting_documents"
    assert resubmitted["document_ids"][:-1] == accepted["document_ids"]  # the original stays
    # A start form opened on the ready revision cannot start the case any more.
    order = basis_document(api)
    response = api.post("hr", f"/cases/{case['id']}/start", {
        "expected_revision": case["revision"], "starts_on": "2026-11-23",
        "basis": {"document_id": order["id"], "reference": "R", "issued_on": "2026-11-21"},
        "confirmation_basis": "x"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "STALE_REVISION"
    submitted = [e for e in api.get("hr", f"/cases/{case['id']}/history").json()["items"]
                 if e["event_type"] == "item.submitted"][-1]
    assert submitted["data"]["revoked_accepted"] is True and submitted["data"]["case_reopened"] is True


def test_correction_without_confirmation_stays_not_sent(api, marina):
    case = started_case(api, marina)
    corrected = api.post("hr", f"/cases/{case['id']}/correct-start", {
        "expected_revision": case["revision"], "starts_on": "2026-11-24", "reason": "Перенос"}).json()
    assert (corrected["starts_on"], corrected["workforce_status"]) == ("2026-11-24", "not_sent")


def test_correction_after_confirmation_needs_review(api, marina):
    case = started_case(api, marina)
    record(api, case)
    corrected = api.post("hr", f"/cases/{case['id']}/correct-start", {
        "expected_revision": current(api, case)["revision"], "starts_on": "2026-11-24",
        "reason": "Дата исправлена"}).json()
    assert corrected["workforce_status"] == "review_required"
    # The previous HR record stays visible next to the new local date.
    assert corrected["workforce_confirmation"]["actual_starts_on"] == "2026-11-23"
    assert corrected["employee_id"] == EMPLOYEE and corrected["workforce_review_reason"] == "Дата исправлена"

    applied = record(api, case, actual="2026-11-24", basis="Поправка внесена в назначение").json()
    assert (applied["workforce_status"], applied["workforce_resolution"]) == ("registered", "corrected")

    api.post("hr", f"/cases/{case['id']}/correct-start", {
        "expected_revision": applied["revision"], "starts_on": "2026-11-25", "reason": "Ещё перенос"})
    kept = record(api, case, actual="2026-11-24", basis="Кадровое основание подтверждает 24 ноября").json()
    assert (kept["workforce_status"], kept["workforce_resolution"]) == ("registered_with_difference", "kept_existing")
    assert kept["starts_on"] == "2026-11-25"  # Hiring keeps its own confirmed date
    assert "2026-11-24" in kept["workforce_review_reason"] and "2026-11-25" in kept["workforce_review_reason"]
    recorded = [e for e in api.get("hr", f"/cases/{case['id']}/history").json()["items"]
                if e["event_type"] == "assignment.recorded"]
    assert len(recorded) == 3 and recorded[-1]["data"]["previous"]["workforce_status"] == "review_required"


def test_record_assignment_with_external_ids(api, marina):
    case = started_case(api, marina)
    response = record(api, case, actual="2026-11-25", system="external").json()
    assert response["workforce_status"] == "registered_with_difference"
    assert response["employee_id"] is None and response["assignment_id"] is None
    assert response["workforce_confirmation"]["employee_ref"] == {"system": "external", "id": EMPLOYEE}
    assert response["workforce_resolution"] is None


def test_record_assignment_requires_started_case(api, marina):
    case = ready_case(api, marina)
    response = record(api, case)
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_STATE"
    assert api.get("hr", f"/cases/{case['id']}/registration-data").status_code == 409


def test_withdrawn_second_candidate_never_starts(api, marina, petr):
    marina_case = create_case(api, marina)
    other = create_case(api, petr, linked=False)
    withdrawn = api.post("hr", f"/cases/{other['id']}/withdraw",
                         {"expected_revision": other["revision"], "reason": "Отказ кандидата"}).json()
    assert (withdrawn["status"], withdrawn["workforce_status"]) == ("withdrawn", "not_sent")
    order = basis_document(api)
    start = api.post("hr", f"/cases/{other['id']}/start", {
        "expected_revision": withdrawn["revision"], "starts_on": "2026-11-23",
        "basis": {"document_id": order["id"], "reference": "R", "issued_on": "2026-11-21"},
        "confirmation_basis": "x"})
    assert start.status_code == 409 and start.json()["error"]["code"] == "INVALID_STATE"
    assert current(api, marina_case)["status"] == "preparing"  # the other case is untouched


def test_candidate_withdraws_own_case_but_not_after_start(api, marina, petr):
    case = create_case(api, marina)
    response = api.post("candidate", f"/cases/{case['id']}/withdraw",
                        {"expected_revision": case["revision"], "reason": "Передумала"})
    assert response.json()["status"] == "withdrawn"
    started = started_case(api, marina)  # a withdrawn case frees the application reference
    assert started["id"] != case["id"]
    refused = api.post("hr", f"/cases/{started['id']}/withdraw",
                       {"expected_revision": started["revision"], "reason": "поздно"})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "INVALID_STATE"


def test_documents_after_start_are_additions(api, marina):
    case = started_case(api, marina)
    added = submit(api, case, "photo", login="hr", kind="hiring_evidence", content=pdf("photo"))
    assert added["status"] == "received" and current(api, case)["status"] == "started"
