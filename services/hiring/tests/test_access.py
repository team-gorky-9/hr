"""Who may see and do what: roles, the other organization, the unlinked candidate, hidden files."""
import pytest

from hiring import auth
from hiring.api import create_app
from tests.conftest import CANDIDATE, basis_document, create_case, current, item, started_case, submit, with_settings


def test_authentication_errors(api):
    assert api.client.get("/api/v1/cases").json()["error"]["code"] == "AUTH_REQUIRED"
    unknown = api.client.get("/api/v1/cases", headers={"Authorization": "Bearer fixture:nobody"})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (401, "INVALID_SESSION")
    real_token = api.client.get("/api/v1/cases", headers={"Authorization": "Bearer abc"})
    assert real_token.status_code == 401


@pytest.mark.parametrize("login", ["department", "employee"])
def test_other_roles_have_no_hiring_access(api, marina, login):
    case = create_case(api, marina)
    assert api.get(login, "/cases").status_code == 403
    assert api.get(login, f"/cases/{case['id']}").status_code == 403
    assert api.upload(login).status_code == 403


def test_candidate_cannot_run_hr_operations(api, marina):
    assert api.post("candidate", "/cases", {"selection": marina, "checklist": [
        {"key": "a", "title": "A", "required": True}], "checklist_version": "1"}).status_code == 403
    case = create_case(api, marina)
    submit(api, case, "passport")
    entry = item(current(api, case), "passport")
    for path, body in [
        (f"/cases/{case['id']}/items/{entry['id']}/review",
         {"expected_revision": entry["revision"], "result": "accepted", "reason": None}),
        (f"/cases/{case['id']}/ready", {"expected_revision": 1}),
        (f"/cases/{case['id']}/request-documents", {"expected_revision": 1, "message": "m"}),
        (f"/cases/{case['id']}/link-account",
         {"expected_revision": 1, "candidate_actor_id": CANDIDATE, "identity_basis": "x"}),
    ]:
        response = api.post("candidate", path, body)
        assert response.status_code == 403, path
    assert api.get("candidate", f"/cases/{case['id']}/registration-data").status_code == 403
    assert api.upload("candidate", "employment_basis").status_code == 403


def test_candidate_cannot_record_assignment(api, marina):
    case = started_case(api, marina)
    response = api.post("candidate", f"/cases/{case['id']}/record-assignment", {
        "expected_revision": case["revision"], "employee_ref": {"system": "workforce", "id": CANDIDATE},
        "assignment_ref": {"system": "workforce", "id": CANDIDATE}, "actual_starts_on": "2026-11-23",
        "confirmation_basis": "я сама"})
    assert response.status_code == 403


def test_other_organization_sees_nothing(api, marina):
    case = started_case(api, marina)
    document_id = item(current(api, case), "passport")["document_ids"][0]
    for path in (f"/cases/{case['id']}", f"/cases/{case['id']}/history", f"/documents/{document_id}",
                 f"/documents/{document_id}/content", f"/cases/{case['id']}/registration-data"):
        response = api.get("hr_other", path)
        assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND"), path
    assert api.get("hr_other", "/cases").json()["items"] == []
    withdraw = api.post("hr_other", f"/cases/{case['id']}/withdraw", {"expected_revision": 1, "reason": "x"})
    assert withdraw.status_code == 404
    foreign = dict(marina, organization_id="00000000-0000-4000-8000-000000000002")
    assert api.post("hr_other", "/cases", {"selection": foreign, "checklist": [
        {"key": "a", "title": "A", "required": True}], "checklist_version": "1"}).status_code == 409


def test_selection_of_another_organization_is_forbidden(api, marina):
    response = api.post("hr_other", "/cases", {"selection": marina, "checklist": [
        {"key": "a", "title": "A", "required": True}], "checklist_version": "1"})
    assert (response.status_code, response.json()["error"]["code"]) == (403, "FORBIDDEN")


def test_unlinked_candidate_sees_no_case_and_no_files(api, marina):
    case = create_case(api, marina, linked=False)
    assert api.get("candidate", "/cases").json()["items"] == []
    assert api.get("candidate", f"/cases/{case['id']}").status_code == 404
    submit(api, case, "passport", login="hr")
    document_id = item(current(api, case), "passport")["document_ids"][0]
    assert api.get("candidate", f"/documents/{document_id}/content").status_code == 404


def test_linked_candidate_reads_case_files_but_not_the_internal_basis(api, marina):
    case = started_case(api, marina)
    hr_file = submit(api, case, "photo", login="hr", kind="hiring_evidence")["document_ids"][-1]
    assert api.get("candidate", f"/documents/{hr_file}/content").status_code == 200
    basis = current(api, case)["basis"]["document_id"]
    assert api.get("candidate", f"/documents/{basis}").status_code == 404
    assert api.get("candidate", f"/documents/{basis}/content").status_code == 404
    assert api.get("hr", f"/documents/{basis}/content").status_code == 200


def test_candidate_cannot_submit_someone_elses_file(api, marina):
    case = create_case(api, marina)
    foreign = api.upload("hr", "hiring_application").json()
    entry = item(current(api, case), "passport")
    response = api.post("candidate", f"/cases/{case['id']}/items/{entry['id']}/submit",
                        {"expected_revision": entry["revision"], "document_id": foreign["id"]})
    assert (response.status_code, response.json()["error"]["field"]) == (422, "document_id")


def test_document_of_another_case_is_rejected(api, marina, petr):
    first = create_case(api, marina)
    second = create_case(api, petr, linked=False)
    used = submit(api, first, "passport", login="hr")["document_ids"][0]
    entry = item(current(api, second), "passport")
    response = api.post("hr", f"/cases/{second['id']}/items/{entry['id']}/submit",
                        {"expected_revision": entry["revision"], "document_id": used})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "INVALID_STATE")


def test_start_basis_must_be_an_employment_basis(api, marina):
    from tests.conftest import ready_case
    case = ready_case(api, marina)
    evidence = api.upload("hr", "hiring_evidence").json()
    response = api.post("hr", f"/cases/{case['id']}/start", {
        "expected_revision": case["revision"], "starts_on": "2026-11-23",
        "basis": {"document_id": evidence["id"], "reference": "R", "issued_on": "2026-11-21"},
        "confirmation_basis": "x"})
    assert (response.status_code, response.json()["error"]["field"]) == (422, "basis.document_id")


def test_link_account_checks_the_candidate_account(api, marina):
    case = create_case(api, marina, linked=False)
    response = api.post("hr", f"/cases/{case['id']}/link-account", {
        "expected_revision": case["revision"], "candidate_actor_id": "00000000-0000-4000-8000-000000000104",
        "identity_basis": "x"})
    assert (response.status_code, response.json()["error"]["field"]) == (422, "candidate_actor_id")
    linked = api.post("hr", f"/cases/{case['id']}/link-account", {
        "expected_revision": case["revision"], "candidate_actor_id": CANDIDATE, "identity_basis": "Паспорт сверен"})
    assert linked.json()["candidate_actor_id"] == CANDIDATE
    assert [c["id"] for c in api.get("candidate", "/cases").json()["items"]] == [case["id"]]


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


def test_workforce_auth_mode(settings, monkeypatch):
    from fastapi.testclient import TestClient
    app = create_app(with_settings(settings, auth_mode="workforce"))
    client = TestClient(app)
    hr = {"actor_id": "00000000-0000-4000-8000-000000000101", "login": "hr",
          "organization_id": "00000000-0000-4000-8000-000000000001",
          "grants": [{"role": "hr", "scope_type": "organization",
                      "scope_id": "00000000-0000-4000-8000-000000000001"}]}
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: FakeResponse(200, hr))
    assert client.get("/api/v1/cases", headers={"Authorization": "Bearer t"}).status_code == 200
    assert client.get("/health").json()["auth_mode"] == "workforce"
    # A fixture token is not a session in workforce mode.
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: FakeResponse(401))
    assert client.get("/api/v1/cases", headers={"Authorization": "Bearer fixture:hr"}).status_code == 401

    def down(*args, **kwargs):
        raise auth.httpx.ConnectError("down")
    monkeypatch.setattr(auth.httpx, "get", down)
    response = client.get("/api/v1/cases", headers={"Authorization": "Bearer t"})
    assert (response.status_code, response.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    app.state.engine.dispose()


def test_basis_document_cannot_move_to_another_case(api, marina, petr):
    from tests.conftest import ready_case
    first = started_case(api, marina)
    basis = current(api, first)["basis"]["document_id"]
    second = ready_case(api, petr)
    response = api.post("hr", f"/cases/{second['id']}/start", {
        "expected_revision": second["revision"], "starts_on": "2026-11-23",
        "basis": {"document_id": basis, "reference": "R", "issued_on": "2026-11-21"}, "confirmation_basis": "x"})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "INVALID_STATE")
    assert basis_document(api)["case_id"] is None
