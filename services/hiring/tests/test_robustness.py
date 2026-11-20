"""Wrong and empty inputs, stale forms, repeated keys and commands, parallel requests, restart."""
import threading
import uuid

from fastapi.testclient import TestClient

from hiring.api import create_app
from tests.conftest import (
    CHECKLIST,
    Api,
    create_case,
    current,
    item,
    pdf,
    ready_case,
    started_case,
    submit,
    with_settings,
)


def error(response):
    return response.status_code, response.json()["error"]["code"], response.json()["error"]["field"]


def test_unknown_and_missing_fields_are_rejected(api, marina):
    body = {"selection": marina, "checklist": CHECKLIST, "checklist_version": "1", "extra": True}
    assert error(api.post("hr", "/cases", body)) == (422, "VALIDATION_ERROR", "extra")
    assert error(api.post("hr", "/cases", {"selection": marina, "checklist": [], "checklist_version": "1"}))[:2] == (
        422, "VALIDATION_ERROR")
    duplicated = [CHECKLIST[0], CHECKLIST[0]]
    assert api.post("hr", "/cases", {"selection": marina, "checklist": duplicated,
                                      "checklist_version": "1"}).status_code == 422
    unlinked_basis = {"selection": marina, "checklist": CHECKLIST, "checklist_version": "1",
                      "candidate_actor_id": "00000000-0000-4000-8000-000000000105"}
    assert api.post("hr", "/cases", unlinked_basis).status_code == 422
    case = create_case(api, marina)
    assert error(api.post("hr", f"/cases/{case['id']}/request-documents",
                          {"expected_revision": case["revision"], "message": "   "}))[:2] == (422, "VALIDATION_ERROR")
    assert api.get("hr", "/cases?status=nonsense").status_code == 422
    assert api.get("hr", "/cases?limit=0").status_code == 422
    assert api.get("hr", "/cases/not-a-uuid").status_code == 422
    assert api.get("hr", f"/cases/{uuid.uuid4()}").status_code == 404


def test_return_requires_a_reason(api, marina):
    case = create_case(api, marina)
    submit(api, case, "passport")
    entry = item(current(api, case), "passport")
    response = api.post("hr", f"/cases/{case['id']}/items/{entry['id']}/review",
                        {"expected_revision": entry["revision"], "result": "needs_revision"})
    assert response.status_code == 422
    unreviewable = item(current(api, case), "education")
    response = api.post("hr", f"/cases/{case['id']}/items/{unreviewable['id']}/review",
                        {"expected_revision": unreviewable["revision"], "result": "accepted"})
    assert error(response)[:2] == (409, "INVALID_STATE")


def test_selection_must_match_the_fixture_source(api, marina):
    changed = dict(marina, decision_basis="Подменённое основание")
    assert error(api.post("hr", "/cases", {"selection": changed, "checklist": CHECKLIST, "checklist_version": "1"}))[
        :2] == (409, "SELECTION_NOT_READY")
    unknown = dict(marina, application_ref={"system": "legacy-hr", "id": str(uuid.uuid4())})
    assert error(api.post("hr", "/cases", {"selection": unknown, "checklist": CHECKLIST, "checklist_version": "1"}))[
        :2] == (409, "SELECTION_NOT_READY")
    rejected = dict(marina, outcome="rejected")
    assert error(api.post("hr", "/cases", {"selection": rejected, "checklist": CHECKLIST, "checklist_version": "1"}))[
        :2] == (409, "SELECTION_NOT_READY")


def test_same_application_returns_the_existing_case(api, marina):
    first = create_case(api, marina)
    again = api.post("hr", "/cases", {"selection": marina, "checklist": CHECKLIST, "checklist_version": "2"})
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    assert again.json()["checklist_version"] == "training-1"
    assert len(api.get("hr", "/cases").json()["items"]) == 1


def test_parallel_creation_makes_one_case(app, marina):
    results = []

    def create():
        with TestClient(app) as client:
            response = Api(client).post("hr", "/cases", {"selection": marina, "checklist": CHECKLIST,
                                                         "checklist_version": "1"})
            results.append((response.status_code, response.json()["id"]))

    threads = [threading.Thread(target=create) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({case_id for _, case_id in results}) == 1
    assert sorted(code for code, _ in results).count(201) == 1


def test_idempotency_key_replays_and_conflicts(api, marina):
    case = create_case(api, marina)
    key = str(uuid.uuid4())
    body = {"expected_revision": case["revision"], "message": "Загрузите документы"}
    first = api.post("hr", f"/cases/{case['id']}/request-documents", body, key=key)
    replay = api.post("hr", f"/cases/{case['id']}/request-documents", body, key=key)
    # The replay comes before the revision check: same status, same body, marked as a replay.
    assert replay.status_code == first.status_code == 200 and replay.json() == first.json()
    assert replay.headers["Idempotency-Replayed"] == "true" and "Idempotency-Replayed" not in first.headers
    other = api.post("hr", f"/cases/{case['id']}/request-documents", dict(body, message="другое"), key=key)
    assert error(other) == (409, "IDEMPOTENCY_CONFLICT", "Idempotency-Key")
    events = [e["event_type"] for e in api.get("hr", f"/cases/{case['id']}/history").json()["items"]]
    assert events.count("documents.requested") == 1
    # The key is scoped by actor: another actor with the same key runs its own command.
    assert api.post("admin", f"/cases/{case['id']}/request-documents", body, key=key).status_code == 409
    assert api.post("hr", "/cases", {"selection": marina, "checklist": CHECKLIST, "checklist_version": "1"},
                    key="not-a-uuid").status_code == 422


def test_create_replay_keeps_201(api, marina):
    key = str(uuid.uuid4())
    body = {"selection": marina, "checklist": CHECKLIST, "checklist_version": "1"}
    first = api.post("hr", "/cases", body, key=key)
    replay = api.post("hr", "/cases", body, key=key)
    assert (first.status_code, replay.status_code) == (201, 201) and first.json()["id"] == replay.json()["id"]


def test_double_command_without_key_is_stale(api, marina):
    case = ready_case(api, marina)
    body = {"expected_revision": case["revision"] - 0, "reason": "Отказ"}
    assert api.post_without_key("hr", f"/cases/{case['id']}/withdraw", body).status_code == 200
    again = api.post_without_key("hr", f"/cases/{case['id']}/withdraw", body)
    assert error(again)[:2] == (409, "STALE_REVISION")


def test_two_tabs_cannot_confirm_a_stale_checklist(api, marina):
    case = create_case(api, marina)
    for key in ("passport", "education"):
        submit(api, case, key)
    tab = current(api, case)  # HR opens the form on this revision
    entry = item(tab, "passport")
    api.post("hr", f"/cases/{case['id']}/items/{entry['id']}/review",
             {"expected_revision": entry["revision"], "result": "accepted"})
    # The second tab still shows the old item revision and the old case revision.
    stale_review = api.post("hr", f"/cases/{case['id']}/items/{entry['id']}/review",
                            {"expected_revision": entry["revision"], "result": "needs_revision", "reason": "x"})
    assert error(stale_review) == (409, "STALE_REVISION", "expected_revision")
    stale_ready = api.post("hr", f"/cases/{case['id']}/ready", {"expected_revision": tab["revision"]})
    assert error(stale_ready)[:2] == (409, "STALE_REVISION")
    assert item(current(api, case), "passport")["status"] == "accepted"


def test_parallel_ready_and_new_file_do_not_pass_an_old_checklist(app, api, marina):
    """Ready and a new submission race on the same revision; the case row lock serializes them,
    so either the file reopens the checklist or ready fails — never ready with an unreviewed file."""
    for _ in range(5):
        case = create_case(api, marina)
        for key in ("passport", "education"):
            submit(api, case, key)
            entry = item(current(api, case), key)
            api.post("hr", f"/cases/{case['id']}/items/{entry['id']}/review",
                     {"expected_revision": entry["revision"], "result": "accepted"})
        snapshot = current(api, case)
        document = api.upload("candidate").json()
        entry = item(snapshot, "education")
        barrier = threading.Barrier(2)

        def ready():
            with TestClient(app) as client:
                barrier.wait()
                Api(client).post("hr", f"/cases/{case['id']}/ready", {"expected_revision": snapshot["revision"]})

        def resubmit():
            with TestClient(app) as client:
                barrier.wait()
                Api(client).post("candidate", f"/cases/{case['id']}/items/{entry['id']}/submit",
                                 {"expected_revision": entry["revision"], "document_id": document["id"]})

        threads = [threading.Thread(target=ready), threading.Thread(target=resubmit)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        final = current(api, case)
        assert not (final["status"] == "ready" and item(final, "education")["status"] != "accepted")
        api.post("hr", f"/cases/{case['id']}/withdraw", {"expected_revision": final["revision"], "reason": "next"})


def test_file_checks(api):
    assert error(api.upload("hr", content=b"")) == (422, "VALIDATION_ERROR", "file")
    assert error(api.upload("hr", content=b"MZ\x90\x00 not a document")) == (422, "VALIDATION_ERROR", "file")
    assert error(api.upload("hr", content=b"%PDF-" + b"x" * 2000)) == (413, "FILE_TOO_LARGE", "file")
    assert error(api.upload("hr", kind="secret")) == (422, "VALIDATION_ERROR", "kind")
    png = api.upload("hr", content=b"\x89PNG\r\n\x1a\n" + b"0" * 10, name="../../etc/passwd.png")
    assert png.status_code == 201
    body = png.json()
    assert (body["media_type"], body["original_name"], body["revision"]) == ("image/png", "passwd.png", 1)


def test_upload_replay_returns_the_same_document(api, settings):
    key = str(uuid.uuid4())
    first = api.upload("hr", content=pdf("same"), key=key)
    replay = api.upload("hr", content=pdf("same"), key=key)
    assert replay.json()["id"] == first.json()["id"] and replay.headers["Idempotency-Replayed"] == "true"
    conflict = api.upload("hr", content=pdf("different"), key=key)
    assert error(conflict)[:2] == (409, "IDEMPOTENCY_CONFLICT")
    folder = settings.file_root / first.json()["organization_id"]
    assert [p.name for p in folder.iterdir()] == [first.json()["id"]]  # no orphan, no temporary file


def test_restart_keeps_data_and_files(settings, marina):
    app = create_app(settings)
    with TestClient(app) as client:
        api = Api(client)
        case = started_case(api, marina)
        document_id = item(current(api, case), "passport")["document_ids"][0]
        original = api.get("hr", f"/documents/{document_id}/content").content
    app.state.engine.dispose()

    restarted = create_app(with_settings(settings))
    with TestClient(restarted) as client:
        api = Api(client)
        again = current(api, case)
        assert (again["status"], again["revision"], again["workforce_status"]) == ("started", case["revision"], "not_sent")
        assert api.get("hr", f"/documents/{document_id}/content").content == original
        assert len(api.get("hr", f"/cases/{case['id']}/history").json()["items"]) == 7  # created, 2×submitted, 2×reviewed, ready, started
    restarted.state.engine.dispose()


def test_manual_confirmed_source_and_pagination(settings, marina):
    app = create_app(with_settings(settings, source_mode="manual-confirmed"))
    with TestClient(app) as client:
        api = Api(client)
        ids = []
        for _ in range(3):
            selection = dict(marina, application_ref={"system": "legacy-hr", "id": str(uuid.uuid4())},
                             is_synthetic=False, decision_basis="Протокол комиссии (введён HR)")
            ids.append(create_case(api, selection, linked=False)["id"])
        assert api.get("hr", f"/cases/{ids[0]}").json()["provenance"]["source_mode"] == "manual-confirmed"
        seen, cursor = [], None
        while True:
            page = api.get("hr", "/cases?limit=2" + (f"&cursor={cursor}" if cursor else "")).json()
            seen += [c["id"] for c in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert seen == ids
        assert api.get("hr", "/cases?cursor=garbage").status_code == 422
    app.state.engine.dispose()
