"""Short wave 2 demonstration through a real HTTP server, using synthetic inputs."""
from tests.conftest import auth_headers, run_alembic_upgrade
from tests.support.http_server import running_server
from tests.test_outbox_and_broker import _prepare_accepted_draft


def test_vacancy_http_path_and_boundaries(make_settings):
    settings = make_settings(rabbitmq_url="amqp://guest:guest@127.0.0.1:1/%2F")
    run_alembic_upgrade(settings.database_url)
    with running_server(settings) as (client, _process):
        hr = auth_headers("hr")
        other = auth_headers("hr_other")
        draft_id, source_id = _prepare_accepted_draft(client)
        approved = client.post(f"/api/v1/drafts/{draft_id}/approve", headers=auth_headers("hr"),
                               json={"expected_revision": 3, "approval_basis": "Учебная публикация"})
        assert approved.status_code == 201, approved.text
        profile_id = approved.json()["id"]
        payload = dict(department_id="00000000-0000-4000-8000-000000000011",
                       position_code="economist-training", title="Экономист",
                       description="Учебная вакансия: финансовые таблицы", profile_id=profile_id)
        created = client.post("/api/v1/catalog/vacancies", headers=hr, json=payload)
        assert created.status_code == 201, created.text
        vacancy_id = created.json()["id"]
        path = f"/api/v1/catalog/vacancies/{vacancy_id}"
        assert client.get("/api/v1/public/vacancies").json() == {"items": []}
        assert client.get(f"/api/v1/public/vacancies/{vacancy_id}").status_code == 404
        assert client.get(path, headers=other).status_code == 404
        assert client.get("/api/v1/catalog/vacancies", headers=other).json() == {"items": []}
        assert client.post("/api/v1/catalog/vacancies", headers=auth_headers("employee"),
                           json=payload).status_code == 403
        # Draft IDs cannot be used as approved profiles; foreign departments are rejected.
        assert client.post("/api/v1/catalog/vacancies", headers=hr,
                           json={**payload, "profile_id": draft_id}).status_code == 404
        assert client.post("/api/v1/catalog/vacancies", headers=hr,
                           json={**payload, "department_id": "00000000-0000-4000-8000-000000000099"}).status_code == 422
        changed = client.patch(path, headers=hr, json={"expected_revision": 1, "title": "Экономист отдела"})
        assert changed.status_code == 200, changed.text
        assert client.patch(path, headers=hr, json={"expected_revision": 1, "title": "Устарело"}).status_code == 409
        published = client.post(path + "/publish", headers=hr, json={"expected_revision": 2})
        assert published.status_code == 200, published.text
        assert published.json()["profile_version"] == 1
        public = client.get("/api/v1/public/vacancies").json()["items"]
        assert len(public) == 1 and public[0]["id"] == vacancy_id
        assert set(public[0]) == {"id", "title", "description", "position_code", "published_at", "organization_id", "department_id", "department_name", "revision", "status"}
        assert public[0]["title"] == "Экономист отдела"
        assert client.patch(path, headers=hr, json={"expected_revision": 3, "title": "Нельзя"}).status_code == 409
        assert client.post(path + "/close", headers=hr, json={"expected_revision": 3, "reason": " "}).status_code == 422
        closed = client.post(path + "/close", headers=hr, json={"expected_revision": 3, "reason": "Учебный набор завершён"})
        assert closed.status_code == 200 and closed.json()["status"] == "closed"
        assert client.get("/api/v1/public/vacancies").json() == {"items": []}
        public_closed = client.get(f"/api/v1/public/vacancies/{vacancy_id}").json()
        assert public_closed["status"] == "closed" and public_closed["revision"] == 3
        assert "profile_id" not in public_closed and "close_reason" not in public_closed
        assert public_closed["organization_id"] == created.json()["organization_id"]
        saved = client.get(path, headers=hr).json()
        assert saved["revision"] == 4
        assert [h["action"] for h in saved["history"]] == ["created", "edited", "published", "closed"]
        assert saved["history"][0]["snapshot"]["title"] == "Экономист"
        assert saved["history"][2]["snapshot"]["status"] == "published"
        assert client.get("/api/v1/catalog/vacancies?status=closed", headers=hr).json()["items"][0]["id"] == vacancy_id
        assert client.get("/ready").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "/api/v1/public/vacancies" in schema["paths"]
        # A draft must not silently publish against a superseded profile.
        pending = client.post("/api/v1/catalog/vacancies", headers=hr, json=payload).json()
        next_draft, _source = _prepare_accepted_draft(client)
        next_profile = client.post(f"/api/v1/drafts/{next_draft}/approve", headers=auth_headers("hr"),
                                   json={"expected_revision": 3, "approval_basis": "Новая учебная редакция"})
        assert next_profile.status_code == 201
        pending_path = f"/api/v1/catalog/vacancies/{pending['id']}"
        rejected = client.post(pending_path + "/publish", headers=hr, json={"expected_revision": 1})
        assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "PROFILE_NOT_READY"
        assert client.get(pending_path, headers=hr).json()["revision"] == 1
        refreshed = client.patch(pending_path, headers=hr,
                                 json={"expected_revision": 1, "profile_id": next_profile.json()["id"]})
        assert refreshed.status_code == 200 and refreshed.json()["profile_version"] == 2
        assert client.post(pending_path + "/publish", headers=hr, json={"expected_revision": 2}).status_code == 200
        print({"source_id": source_id, "profile_id": profile_id, "vacancy_id": vacancy_id,
               "revision": saved["revision"], "status": saved["status"]})
