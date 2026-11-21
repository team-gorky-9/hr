"""candidate-portal 5A: собственное обращение кандидата (wave-5-candidate-portal-stage-1)."""
import uuid

from tests.conftest import pdf

ECONOMIST = {"system": "catalog", "id": "00000000-0000-4000-8000-000000000c01", "revision": 1}
CLOSED = {"system": "catalog", "id": "00000000-0000-4000-8000-000000000c02", "revision": 1}
CONTACT = {"channel": "email", "value": "candidate@example.test"}
PATH = "/candidate-requests"


def create(api, login="candidate", **body):
    response = api.post(login, PATH, {"message": "Хочу работать в администрации (учебно)", "contact": CONTACT} | body)
    assert response.status_code == 201, response.text
    return response.json()


def upload(api, login, request_id, content=None, kind="candidate_resume", name="resume.pdf"):
    return api.client.post(f"/api/v1{PATH}/{request_id}/documents", headers=api.headers(login, str(uuid.uuid4())),
                           data={"kind": kind}, files={"file": (name, content or pdf(name), "application/pdf")})


def submit(api, login, row):
    response = api.post(login, f"{PATH}/{row['id']}/submit", {"expected_revision": row["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_two_candidates_submit_and_see_only_their_own(api):
    vacancies = api.get("candidate", "/candidate-portal/vacancies").json()
    assert vacancies["source"] == "training_snapshot" and [v["ref"]["id"] for v in vacancies["items"]] == [ECONOMIST["id"]]

    first = create(api, vacancy_ref=ECONOMIST)
    assert (first["status"], first["number"], first["target_question"]) == ("draft", None, None)
    assert first["vacancy"]["title"].startswith("Экономист")
    assert first["contact"] == CONTACT | {"source": "candidate_reported", "verified": False}
    resume = upload(api, "candidate", first["id"])
    assert resume.status_code == 201, resume.text
    first = submit(api, "candidate", api.get("candidate", f"{PATH}/{first['id']}").json())
    assert first["status"] == "submitted" and first["number"].startswith("ОБР-") and first["submitted_at"]

    second = create(api, "candidate2", message="Ищу любую работу по специальности (учебно)")
    assert second["target_question"] == "no_target" and second["vacancy_ref"] is None
    second = submit(api, "candidate2", second)
    assert second["number"] != first["number"]

    assert [r["id"] for r in api.get("candidate", PATH).json()["items"]] == [first["id"]]
    assert [r["id"] for r in api.get("candidate2", PATH).json()["items"]] == [second["id"]]
    assert api.get("candidate2", f"{PATH}/{first['id']}").status_code == 404
    document_id = first["documents"][0]["id"]
    assert api.get("candidate2", f"{PATH}/{first['id']}/documents/{document_id}/content").status_code == 404
    assert api.get("candidate2", f"/documents/{document_id}/content").status_code == 404
    assert api.get("candidate", f"{PATH}/{first['id']}/documents/{document_id}/content").content == pdf("resume.pdf")

    queue = api.get("hr", PATH).json()["items"]
    assert {r["number"] for r in queue} == {first["number"], second["number"]}
    hr_view = api.get("hr", f"{PATH}/{first['id']}").json()
    assert hr_view["author_actor_id"] == "00000000-0000-4000-8000-000000000105"
    assert hr_view["submitted_snapshot"]["document_ids"] == [document_id]
    assert api.get("hr", f"{PATH}/{first['id']}/documents/{document_id}/content").status_code == 200
    assert api.get("hr_other", PATH).json()["items"] == []
    assert api.get("hr_other", f"{PATH}/{first['id']}").status_code == 404


def test_new_resume_keeps_original_and_drafts_are_private(api):
    row = create(api)
    one = upload(api, "candidate", row["id"], content=pdf("v1"), name="resume-v1.pdf").json()
    # HR не видит черновик и его файлы.
    assert api.get("hr", f"{PATH}/{row['id']}").status_code == 404
    assert api.get("hr", f"/documents/{one['id']}/content").status_code == 404
    assert api.get("hr", PATH).json()["items"] == []
    row = submit(api, "candidate", api.get("candidate", f"{PATH}/{row['id']}").json())
    two = upload(api, "candidate", row["id"], content=pdf("v2"), kind="candidate_addendum", name="resume-v2.pdf").json()
    documents = api.get("candidate", f"{PATH}/{row['id']}").json()["documents"]
    assert [d["id"] for d in documents] == [one["id"], two["id"]]
    assert api.get("candidate", f"{PATH}/{row['id']}/documents/{one['id']}/content").content == pdf("v1")
    # Снимок подачи не переписан поздним файлом.
    assert api.get("hr", f"{PATH}/{row['id']}").json()["submitted_snapshot"]["document_ids"] == [one["id"]]


def test_closed_or_unknown_vacancy_keeps_the_target_question(api):
    closed = create(api, vacancy_ref=CLOSED)
    assert closed["target_question"] == "vacancy_closed"
    unknown = create(api, "candidate2", vacancy_ref=ECONOMIST | {"revision": 7})
    assert unknown["target_question"] == "vacancy_unknown" and unknown["vacancy"] is None
    submitted = submit(api, "candidate", closed)
    assert (submitted["status"], submitted["target_question"]) == ("submitted", "vacancy_closed")
    # Выбор вакансии в черновике и отказ от неё.
    edited = api.client.patch(f"/api/v1{PATH}/{unknown['id']}", headers=api.headers("candidate2", str(uuid.uuid4())),
                              json={"expected_revision": unknown["revision"], "vacancy_ref": ECONOMIST}).json()
    assert edited["target_question"] is None and edited["revision"] == 2
    cleared = api.client.patch(f"/api/v1{PATH}/{unknown['id']}", headers=api.headers("candidate2", str(uuid.uuid4())),
                               json={"expected_revision": 2, "clear_vacancy": True}).json()
    assert cleared["target_question"] == "no_target"


def test_author_from_session_roles_and_states(api):
    # actor_id в теле не принимается: автор — актор входа.
    spoofed = api.post("candidate", PATH, {"message": "x" * 10, "contact": CONTACT,
                                           "author_actor_id": "00000000-0000-4000-8000-000000000107"})
    assert spoofed.status_code == 422
    assert api.post("hr", PATH, {"message": "Обращение от HR", "contact": CONTACT}).status_code == 403
    assert api.post("department", PATH, {"message": "Обращение", "contact": CONTACT}).status_code == 403
    row = create(api)
    patch = lambda login, body: api.client.patch(f"/api/v1{PATH}/{row['id']}",  # noqa: E731
                                                 headers=api.headers(login, str(uuid.uuid4())), json=body)
    assert patch("candidate2", {"expected_revision": 1, "message": "чужая правка"}).status_code == 404
    assert patch("candidate", {"expected_revision": 9, "message": "устаревшая форма"}).json()["error"]["code"] == "STALE_REVISION"
    assert upload(api, "candidate2", row["id"]).status_code == 404
    assert upload(api, "candidate", row["id"], content=b"MZ not a pdf").status_code == 422
    submitted = submit(api, "candidate", row)
    assert patch("candidate", {"expected_revision": submitted["revision"], "message": "после подачи"}).json()["error"]["code"] == "INVALID_STATE"
    again = api.post("candidate", f"{PATH}/{row['id']}/submit", {"expected_revision": submitted["revision"]})
    assert again.json()["error"]["code"] == "INVALID_STATE"
    assert api.post("candidate", PATH, {"message": "нет контакта"}).status_code == 422
    history = [e["event_type"] for e in api.get("candidate", f"{PATH}/{row['id']}/history").json()["items"]]
    assert history == ["request.created", "request.submitted"]
