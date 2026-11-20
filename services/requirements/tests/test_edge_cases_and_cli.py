"""Дополнительные проверки edge-cases: пагинация, /documents, /ready 503, OpenAPI, две вкладки и CLI."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
import uuid

from fastapi.testclient import TestClient
import httpx

from requirements_service.api.app import create_app
from requirements_service.seed import seed_positions
from requirements_service.db.session import create_db_engine, create_session_factory
from tests.conftest import (
    ACTOR_CAND_1,
    ACTOR_DEPT_1,
    ACTOR_HR_OTHER,
    ORG_1,
    SERVICE_ROOT,
    auth_headers,
    run_alembic_upgrade,
)
from tests.test_e2e_acceptance import _make_economist_draft
from tests.test_errors_security_concurrency import _upload_txt_source


def test_standalone_documents_path_traversal_and_invalid_mime(env):
    _app, client, settings, _broker = env

    # Path traversal в filename не создаёт файл вне FILE_ROOT.
    resp = client.post(
        "/api/v1/documents",
        headers=auth_headers("hr"),
        files={"file": ("../../evil/notes.txt", b"safe bytes", "text/plain")},
        data={"kind": "regulation"},
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["original_name"] == "notes.txt"
    doc_id = doc["id"]
    expected_path = settings.file_root.resolve() / ORG_1 / uuid.UUID(doc_id).hex[:2] / uuid.UUID(doc_id).hex
    assert expected_path.is_file()

    # Недопустимое расширение (.exe) -> 422 VALIDATION_ERROR.
    bad = client.post(
        "/api/v1/documents",
        headers=auth_headers("hr"),
        files={"file": ("payload.exe", b"MZ", "application/x-msdownload")},
        data={"kind": "other"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_pagination_cursors_and_openapi(env):
    _app, client, _settings, _broker = env

    # OpenAPI доступен по /openapi.json.
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/drafts/{draft_id}/approve" in paths
    assert "/api/v1/positions/{position_code}/approved-profile" in paths

    for i in range(3):
        r = client.post(
            "/api/v1/positions",
            headers=auth_headers("hr"),
            json={"code": f"pos-{i}", "title": f"Должность {i}"},
        )
        assert r.status_code == 201

    collected = []
    cursor = None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = client.get(
            "/api/v1/positions",
            headers={"Authorization": "Bearer fixture:hr"},
            params=params,
        )
        assert page.status_code == 200
        body = page.json()
        collected.extend(item["code"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    # 1 seeded (economist-training) + 3 created = 4 уникальные должности.
    assert len(collected) == 4
    assert len(set(collected)) == 4

    # Поддельный cursor -> 422 VALIDATION_ERROR.
    bad_cursor = client.get(
        "/api/v1/positions",
        headers={"Authorization": "Bearer fixture:hr"},
        params={"cursor": "not-valid-base64"},
    )
    assert bad_cursor.status_code == 422


def test_submit_validation_edit_clears_review_and_two_tabs_same_draft(env):
    _app, client, _settings, _broker = env
    src = _upload_txt_source(client)
    src_id = src["id"]
    content = _make_economist_draft(src_id)
    draft = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr"),
        json={"position_code": "economist-training", "content": content},
    ).json()
    draft_id = draft["id"]

    # Назначение на candidate или чужую организацию -> 422 VALIDATION_ERROR.
    for bad_actor in (ACTOR_CAND_1, ACTOR_HR_OTHER, str(uuid.uuid4())):
        bad_sub = client.post(
            f"/api/v1/drafts/{draft_id}/submit",
            headers=auth_headers("hr"),
            json={"expected_revision": 1, "reviewer_actor_id": bad_actor},
        )
        assert bad_sub.status_code == 422
        assert bad_sub.json()["error"]["field"] == "reviewer_actor_id"

    # Направляем, принимаем? Нет — возвращаем с замечанием, затем правим и повторно направляем:
    # без нового согласования approve запрещён.
    client.post(
        f"/api/v1/drafts/{draft_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("department"),
        json={"expected_revision": 2, "result": "returned", "note": "Нужна правка"},
    )
    edited = deepcopy(content)
    edited["note"] = "Исправлено"
    client.patch(
        f"/api/v1/drafts/{draft_id}",
        headers=auth_headers("hr"),
        json={"expected_revision": 3, "content": edited, "change_reason": "Правка"},
    )
    client.post(
        f"/api/v1/drafts/{draft_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 4, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    unapproved = client.post(
        f"/api/v1/drafts/{draft_id}/approve",
        headers=auth_headers("hr"),
        json={"expected_revision": 5, "approval_basis": "Без review"},
    )
    assert unapproved.status_code == 409
    assert unapproved.json()["error"]["code"] == "INVALID_STATE"

    # Теперь согласуем и запускаем 2 вкладки (concurrent approve ОДНОГО черновика с разными ключами).
    client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("department"),
        json={"expected_revision": 5, "result": "accepted", "note": "Принято"},
    )
    barrier = Barrier(2)

    def tab_approve(_):
        barrier.wait(timeout=5)
        return client.post(
            f"/api/v1/drafts/{draft_id}/approve",
            headers=auth_headers("hr"),
            json={"expected_revision": 6, "approval_basis": "Параллельная вкладка"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(tab_approve, range(2)))

    codes = sorted(r.status_code for r in results)
    assert codes == [201, 409]
    conflict_resp = [r for r in results if r.status_code == 409][0]
    assert conflict_resp.json()["error"]["code"] == "STALE_REVISION"


def test_ready_returns_503_before_migrations_and_workforce_mode_health(make_settings, broker):
    settings = make_settings(seed_on_startup=False)
    app = create_app(settings, publisher=broker)
    with TestClient(app) as client:
        # До применения миграций /ready должен вернуть 503.
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["status"] == "unavailable"

    # Проверка AUTH_MODE=workforce в /health (без приема fixture:hr).
    wf_settings = make_settings(auth_mode="workforce", seed_on_startup=False)
    run_alembic_upgrade(wf_settings.database_url)
    wf_app = create_app(wf_settings, publisher=broker)
    with TestClient(wf_app) as wf_client:
        health = wf_client.get("/health")
        assert health.status_code == 200
        assert health.json()["auth_mode"] == "workforce"


def test_seed_idempotency_and_cli_modules(make_settings, tmp_path: Path):
    settings = make_settings(seed_on_startup=False)
    run_alembic_upgrade(settings.database_url)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            first = seed_positions(
                session,
                org_path=settings.fixture_org_path,
                default_organization_id=uuid.UUID(settings.seed_organization_id),
            )
            session.commit()
            second = seed_positions(
                session,
                org_path=settings.fixture_org_path,
                default_organization_id=uuid.UUID(settings.seed_organization_id),
            )
            session.commit()
        assert first == 1
        assert second == 0
    finally:
        engine.dispose()

    # Проверка запуска CLI модулей seed и outbox через отдельный процесс.
    env_vars = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "FILE_ROOT": str(tmp_path / "cli_files"),
    }
    seed_proc = subprocess.run(
        [sys.executable, "-m", "requirements_service.seed"],
        cwd=SERVICE_ROOT,
        env=env_vars,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "seeded positions: 0" in seed_proc.stdout

    outbox_proc = subprocess.run(
        [sys.executable, "-m", "requirements_service.messaging.outbox", "--once"],
        cwd=SERVICE_ROOT,
        env=env_vars,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "outbox flushed: sent=0" in outbox_proc.stdout
