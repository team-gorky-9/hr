"""Сквозная приёмка на одном примере из wave-1-denis-requirements."""
from copy import deepcopy
from pathlib import Path
import uuid

from tests.conftest import ACTOR_DEPT_1, ACTOR_HR_1, ORG_1, auth_headers
from tests.support.consumer import RequirementsApprovedConsumer

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "wave-1"


def _make_economist_draft(source_id: str, *, extra_note: str = "Начальная версия") -> dict:
    return {
        "schema_version": "requirement-draft/1.0",
        "position_code": "economist-training",
        "is_synthetic": True,
        "note": extra_note,
        "sources": [
            {
                "source_document_id": source_id,
                "role": "job_description",
                "observed_revision": "1.0",
                "is_primary": True,
            }
        ],
        "formal_requirements": [
            {
                "key": "econ.experience.relevant",
                "kind": "experience",
                "description": "Проверка расчётов и составление финансовых таблиц",
                "params": {
                    "schema_version": "0.1",
                    "scope": "relevant_role",
                    "minimum_defined": False,
                    "relevance_hint": "составление финансовых таблиц и проверка исходных сумм",
                },
                "is_mandatory": True,
                "verification": "resume",
                "origin": "source",
                "source_refs": [
                    {
                        "source_document_id": source_id,
                        "address": "абз. 2",
                        "quote": "Сотрудник составляет финансовые таблицы и проверяет исходные суммы.",
                    }
                ],
            }
        ],
        "competencies": [
            {
                "key": "econ.analytics",
                "code": "ECON-ANL",
                "name": "Финансовый анализ и объяснение расхождений",
                "origin": "source",
                "source_refs": [
                    {
                        "source_document_id": source_id,
                        "address": "абз. 3",
                        "quote": "Сотрудник объясняет выявленные расхождения в расчёте.",
                    }
                ],
                "indicators": [
                    {
                        "key": "econ.analytics.variance",
                        "text": "Объясняет выявленные расхождения в расчёте",
                        "is_mandatory": True,
                        "verification": "interview",
                        "origin": "source",
                        "source_refs": [
                            {
                                "source_document_id": source_id,
                                "address": "абз. 3",
                                "quote": "Сотрудник объясняет выявленные расхождения в расчёте.",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_full_acceptance_path_v1_to_v2_and_consumer_validation(env, tmp_path: Path):
    app, client, _settings, broker = env

    # 0. Учебная должность economist-training загружена при старте, /health отмечает auth_mode=fixture.
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["auth_mode"] == "fixture"

    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json() == {
        "status": "ok",
        "db": "ok",
        "migrations": "ok",
        "broker": "ok",
        "auth_mode": "fixture",
    }

    positions = client.get("/api/v1/positions", headers={"Authorization": "Bearer fixture:hr"})
    assert positions.status_code == 200
    assert any(p["code"] == "economist-training" for p in positions.json()["items"])

    # 1. Загрузить учебную ДИ.
    jd_bytes = (FIXTURES_DIR / "job-description.txt").read_bytes()
    src_resp = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={"file": ("job-description.txt", jd_bytes, "text/plain")},
        data={"position_code": "economist-training"},
    )
    assert src_resp.status_code == 201, src_resp.text
    source_data = src_resp.json()
    source_id = source_data["id"]
    assert source_data["extraction_status"] == "ready"
    assert "Сотрудник составляет финансовые таблицы" in source_data["extracted_text"]

    # /documents маршруты common также доступны для источника.
    doc_meta = client.get(f"/api/v1/documents/{source_id}", headers={"Authorization": "Bearer fixture:hr"})
    assert doc_meta.status_code == 200
    assert doc_meta.json()["sha256"] == source_data["sha256"]
    doc_bytes = client.get(
        f"/api/v1/documents/{source_id}/content",
        headers={"Authorization": "Bearer fixture:hr"},
    )
    assert doc_bytes.status_code == 200
    assert doc_bytes.content == jd_bytes

    # 2. Создать валидный черновик v1.
    draft_content = _make_economist_draft(source_id)
    create_resp = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr"),
        json={"position_code": "economist-training", "content": draft_content},
    )
    assert create_resp.status_code == 201, create_resp.text
    draft_v1 = create_resp.json()
    draft_v1_id = draft_v1["id"]
    assert draft_v1["status"] == "editing"
    assert draft_v1["revision"] == 1
    assert draft_v1["content_revision"] == 1
    assert draft_v1["contour"] == "training"

    # Направить на согласование department.
    submit_resp = client.post(
        f"/api/v1/drafts/{draft_v1_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["status"] == "in_review"
    assert submit_resp.json()["revision"] == 2
    assert submit_resp.json()["content_revision"] == 1

    # 3. Согласующий возвращает замечание.
    dept_view = client.get(f"/api/v1/drafts/{draft_v1_id}", headers={"Authorization": "Bearer fixture:department"})
    assert dept_view.status_code == 200
    return_resp = client.post(
        f"/api/v1/drafts/{draft_v1_id}/review",
        headers=auth_headers("department"),
        json={
            "expected_revision": 2,
            "result": "returned",
            "note": "Уточнить формулировку показателя расхождений",
        },
    )
    assert return_resp.status_code == 200
    assert return_resp.json()["status"] == "returned"
    assert return_resp.json()["revision"] == 3
    assert return_resp.json()["review_note"] == "Уточнить формулировку показателя расхождений"

    # HR исправляет черновик -> content_revision растёт до 2.
    fixed_content = deepcopy(draft_content)
    fixed_content["note"] = "Исправлено по замечанию отдела"
    patch_resp = client.patch(
        f"/api/v1/drafts/{draft_v1_id}",
        headers=auth_headers("hr"),
        json={
            "expected_revision": 3,
            "content": fixed_content,
            "change_reason": "Уточнена формулировка по замечанию согласующего",
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["revision"] == 4
    assert patch_resp.json()["content_revision"] == 2

    # Повторно направить и согласовать.
    submit2 = client.post(
        f"/api/v1/drafts/{draft_v1_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 4, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    assert submit2.status_code == 200
    assert submit2.json()["revision"] == 5

    accept_resp = client.post(
        f"/api/v1/drafts/{draft_v1_id}/review",
        headers=auth_headers("department"),
        json={
            "expected_revision": 5,
            "result": "accepted",
            "note": "Согласовано редакция 2",
        },
    )
    assert accept_resp.status_code == 200
    accepted_draft = accept_resp.json()
    assert accepted_draft["status"] == "in_review"
    assert accepted_draft["revision"] == 6
    assert accepted_draft["accepted_content_revision"] == 2
    assert accepted_draft["accepted_source_revisions"] == {source_id: 1}

    # HR утверждает v1.
    corr_id = str(uuid.uuid4())
    approve_headers = auth_headers("hr")
    approve_headers["X-Correlation-Id"] = corr_id
    approve_resp = client.post(
        f"/api/v1/drafts/{draft_v1_id}/approve",
        headers=approve_headers,
        json={"expected_revision": 6, "approval_basis": "Учебный пример утверждён"},
    )
    assert approve_resp.status_code == 201, approve_resp.text
    profile_v1 = approve_resp.json()
    v1_id = profile_v1["id"]
    assert profile_v1["version"] == 1
    assert profile_v1["contour"] == "training"
    assert profile_v1["is_current"] is True
    assert profile_v1["approved_by_actor_id"] == ACTOR_HR_1
    assert profile_v1["sources_snapshot"][0]["source_document_id"] == source_id
    assert profile_v1["sources_snapshot"][0]["source_revision"] == 1

    # 4. Outbox отправляет requirements.approved; подписчик читает по HTTP и валидирует v1.
    assert app.state.outbox_relay.flush_once() == 1
    deliveries = client.get("/api/v1/deliveries?status=sent", headers={"Authorization": "Bearer fixture:hr"})
    assert deliveries.status_code == 200
    assert len(deliveries.json()["items"]) == 1

    consumer = RequirementsApprovedConsumer(
        db_path=tmp_path / "consumer.db",
        fetch_profile_http=lambda pid, _org: (
            client.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).status_code,
            client.get(f"/api/v1/profiles/{pid}", headers={"Authorization": "Bearer fixture:hr"}).json(),
        ),
        allowed_organization_ids={ORG_1},
    )
    assert consumer.consume_one_in_memory(broker) == "processed"
    received = consumer.list_received_profiles()
    assert len(received) == 1
    assert received[0]["profile_id"] == v1_id
    assert received[0]["profile_version"] == 1

    # 5. Создать draft v2 из v1 -> current всё ещё отдаёт v1.
    revise_resp = client.post(
        f"/api/v1/profiles/{v1_id}/revise",
        headers=auth_headers("hr"),
        json={"change_reason": "Плановое обновление v2"},
    )
    assert revise_resp.status_code == 201
    draft_v2 = revise_resp.json()
    draft_v2_id = draft_v2["id"]
    assert draft_v2["status"] == "editing"

    current_before_v2 = client.get(
        "/api/v1/positions/economist-training/approved-profile?contour=training",
        headers={"Authorization": "Bearer fixture:hr"},
    )
    assert current_before_v2.status_code == 200
    assert current_before_v2.json()["id"] == v1_id

    # Изменить v2, согласовать и утвердить.
    v2_content = deepcopy(draft_v2["content"])
    v2_content["note"] = "Редакция 2 для учебного профиля"
    p2 = client.patch(
        f"/api/v1/drafts/{draft_v2_id}",
        headers=auth_headers("hr"),
        json={"expected_revision": 1, "content": v2_content, "change_reason": "Обновление note для v2"},
    )
    assert p2.status_code == 200
    s2 = client.post(
        f"/api/v1/drafts/{draft_v2_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 2, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    assert s2.status_code == 200
    r2 = client.post(
        f"/api/v1/drafts/{draft_v2_id}/review",
        headers=auth_headers("department"),
        json={"expected_revision": 3, "result": "accepted", "note": "Принято v2"},
    )
    assert r2.status_code == 200
    a2 = client.post(
        f"/api/v1/drafts/{draft_v2_id}/approve",
        headers=auth_headers("hr"),
        json={"expected_revision": 4, "approval_basis": "Утверждена версия 2"},
    )
    assert a2.status_code == 201
    profile_v2 = a2.json()
    assert profile_v2["version"] == 2
    assert profile_v2["is_current"] is True

    # v1 читается по прежнему ID с исходным содержимым; current отдаёт v2.
    read_v1 = client.get(f"/api/v1/profiles/{v1_id}", headers={"Authorization": "Bearer fixture:hr"})
    assert read_v1.status_code == 200
    assert read_v1.json()["version"] == 1
    assert read_v1.json()["is_current"] is False
    assert read_v1.json()["content"]["note"] == "Исправлено по замечанию отдела"

    read_current = client.get(
        "/api/v1/positions/economist-training/approved-profile?contour=training",
        headers={"Authorization": "Bearer fixture:hr"},
    )
    assert read_current.status_code == 200
    assert read_current.json()["id"] == profile_v2["id"]
    assert read_current.json()["version"] == 2
    assert read_current.json()["content"]["note"] == "Редакция 2 для учебного профиля"

    # Рабочий контур по-прежнему пуст -> 404 NO_APPROVED_PROFILE.
    working_current = client.get(
        "/api/v1/positions/economist-training/approved-profile?contour=working",
        headers={"Authorization": "Bearer fixture:hr"},
    )
    assert working_current.status_code == 404
    assert working_current.json()["error"]["code"] == "NO_APPROVED_PROFILE"

    # История черновика v1 содержит полный аудит.
    history = client.get(
        f"/api/v1/drafts/{draft_v1_id}/history",
        headers={"Authorization": "Bearer fixture:hr"},
    )
    assert history.status_code == 200
    actions = [ev["action"] for ev in history.json()["items"]]
    assert actions == [
        "created",
        "submitted",
        "review_returned",
        "edited",
        "submitted",
        "review_accepted",
        "approved",
    ]
