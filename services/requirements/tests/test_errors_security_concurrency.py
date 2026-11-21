"""Тесты ошибок, изоляции организаций, прав доступа, сканов, идемпотентности и конкурентности."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
from pathlib import Path
from threading import Barrier
import uuid
import zipfile

from fastapi.testclient import TestClient
import httpx
from pypdf import PdfWriter

from requirements_service.api.app import create_app
from requirements_service.auth import WorkforceActorDirectory
from tests.conftest import (
    ACTOR_DEPT_1,
    ACTOR_HR_1,
    ORG_1,
    auth_headers,
    run_alembic_upgrade,
)
from tests.test_e2e_acceptance import _make_economist_draft


def _make_docx_bytes(paragraphs: list[str], table_row: list[str] | None = None) -> bytes:
    body_xml = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs
    )
    if table_row:
        cells = "".join(
            f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in table_row
        )
        body_xml += f"<w:tbl><w:tr>{cells}</w:tr></w:tbl>"
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
    return buf.getvalue()


def _make_blank_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_text_pdf_bytes(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream)} >> stream\n".encode("ascii") + stream + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(buf.tell())
        buf.write(obj)
    xref_pos = buf.tell()
    buf.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode("ascii"))
    buf.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii"))
    return buf.getvalue()


def _upload_txt_source(client: TestClient, text: str = "Сотрудник составляет финансовые таблицы и проверяет исходные суммы.\nСотрудник объясняет выявленные расхождения в расчёте.") -> dict:
    resp = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={"file": ("jd.txt", text.encode("utf-8"), "text/plain")},
        data={"position_code": "economist-training"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_auth_roles_and_workforce_directory_errors(env):
    _app, client, _settings, _broker = env

    # Без токена -> 401.
    no_auth = client.get("/api/v1/positions")
    assert no_auth.status_code == 401
    assert no_auth.json()["error"]["code"] == "AUTH_REQUIRED"

    # Не-fixture токен в fixture режиме -> 401.
    bad_tok = client.get("/api/v1/positions", headers={"Authorization": "Bearer secret-jwt"})
    assert bad_tok.status_code == 401
    assert bad_tok.json()["error"]["code"] == "INVALID_SESSION"

    # candidate и employee не имеют доступа к служебным операциям требований.
    for role in ("candidate", "employee"):
        r1 = client.get("/api/v1/positions", headers={"Authorization": f"Bearer fixture:{role}"})
        assert r1.status_code == 403
        r2 = client.get("/api/v1/drafts", headers={"Authorization": f"Bearer fixture:{role}"})
        assert r2.status_code == 403
        r3 = client.get("/api/v1/deliveries", headers={"Authorization": f"Bearer fixture:{role}"})
        assert r3.status_code == 403

    # department не может создавать должности и смотреть deliveries.
    dept_pos = client.post(
        "/api/v1/positions",
        headers=auth_headers("department"),
        json={"code": "new-pos", "title": "Новая"},
    )
    assert dept_pos.status_code == 403
    dept_del = client.get("/api/v1/deliveries", headers={"Authorization": "Bearer fixture:department"})
    assert dept_del.status_code == 403

    # Проверка WorkforceActorDirectory при 200, 401 и 503.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") == "Bearer valid-tok":
            return httpx.Response(
                200,
                json={
                    "actor": {
                        "actor_id": ACTOR_HR_1,
                        "login": "hr",
                        "organization_id": ORG_1,
                        "grants": [{"role": "hr", "scope_type": "organization", "scope_id": ORG_1}],
                        "active": True,
                    }
                },
            )
        if request.headers.get("Authorization") == "Bearer down-tok":
            return httpx.Response(503, json={"error": {"code": "DOWN"}})
        return httpx.Response(401, json={"error": {"code": "INVALID_SESSION"}})

    wf_client = httpx.Client(transport=httpx.MockTransport(handler))
    directory = WorkforceActorDirectory("http://workforce.local", client=wf_client)
    actor = directory.authenticate_bearer("Bearer valid-tok")
    assert str(actor.actor_id) == ACTOR_HR_1

    try:
        directory.authenticate_bearer("Bearer bad-tok")
        assert False, "expected 401"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401

    try:
        directory.authenticate_bearer("Bearer down-tok")
        assert False, "expected 503"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503


def test_cross_org_isolation_and_admin_override(env):
    _app, client, _settings, _broker = env
    src = _upload_txt_source(client)
    src_id = src["id"]
    draft_resp = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr"),
        json={"position_code": "economist-training", "content": _make_economist_draft(src_id)},
    )
    draft_id = draft_resp.json()["id"]

    # Чужая организация hr_other видит пустые списки и получает 404 без утечки данных.
    assert client.get("/api/v1/positions", headers={"Authorization": "Bearer fixture:hr_other"}).json()["items"] == []
    assert client.get("/api/v1/drafts", headers={"Authorization": "Bearer fixture:hr_other"}).json()["items"] == []
    assert client.get(f"/api/v1/sources/{src_id}", headers={"Authorization": "Bearer fixture:hr_other"}).status_code == 404
    assert client.get(f"/api/v1/documents/{src_id}", headers={"Authorization": "Bearer fixture:hr_other"}).status_code == 404
    assert client.get(f"/api/v1/drafts/{draft_id}", headers={"Authorization": "Bearer fixture:hr_other"}).status_code == 404
    assert client.get(f"/api/v1/drafts/{draft_id}/history", headers={"Authorization": "Bearer fixture:hr_other"}).status_code == 404

    # Попытка hr_other сослаться на source_id чужой организации даёт ту же ошибку, что и неизвестный UUID.
    foreign_draft = _make_economist_draft(src_id)
    foreign_draft["position_code"] = "other-pos"
    client.post(
        "/api/v1/positions",
        headers=auth_headers("hr_other"),
        json={"code": "other-pos", "title": "Чужая должность"},
    )
    bad_foreign = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr_other"),
        json={"position_code": "other-pos", "content": foreign_draft},
    )
    unknown_draft = _make_economist_draft(str(uuid.uuid4()))
    unknown_draft["position_code"] = "other-pos"
    bad_unknown = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr_other"),
        json={"position_code": "other-pos", "content": unknown_draft},
    )
    assert bad_foreign.status_code == 422
    assert bad_foreign.json()["error"]["code"] == "SOURCE_NOT_FOUND"
    assert bad_unknown.status_code == 422
    assert bad_unknown.json()["error"]["code"] == "SOURCE_NOT_FOUND"

    # Неназначенный department не видит чужой draft/source -> 403.
    assert client.get(f"/api/v1/drafts/{draft_id}", headers={"Authorization": "Bearer fixture:department"}).status_code == 403
    assert client.get(f"/api/v1/sources/{src_id}", headers={"Authorization": "Bearer fixture:department"}).status_code == 403

    # Назначение на department; неназначенный HR не может провести review; admin без override_reason -> 422.
    sub = client.post(
        f"/api/v1/drafts/{draft_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
    )
    assert sub.status_code == 200

    hr_review = client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("hr"),
        json={"expected_revision": 2, "result": "accepted", "note": "сам себе"},
    )
    assert hr_review.status_code == 403

    admin_no_reason = client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("admin"),
        json={"expected_revision": 2, "result": "accepted", "note": "срочно"},
    )
    assert admin_no_reason.status_code == 422
    assert admin_no_reason.json()["error"]["field"] == "override_reason"

    admin_ok = client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("admin"),
        json={
            "expected_revision": 2,
            "result": "accepted",
            "note": "Согласовано замещением",
            "override_reason": "Руководитель отдела в отпуске",
        },
    )
    assert admin_ok.status_code == 200


def test_docx_text_pdf_scanned_pdf_and_manual_transcription(env):
    _app, client, _settings, _broker = env

    # 1. DOCX извлекается корректно (абзацы + таблица).
    docx_bytes = _make_docx_bytes(
        ["Должностная инструкция экономиста"],
        table_row=["Обязанность", "Проверка сумм"],
    )
    docx_resp = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={
            "file": (
                "jd.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"position_code": "economist-training"},
    )
    assert docx_resp.status_code == 201
    assert docx_resp.json()["extraction_status"] == "ready"
    assert "Проверка сумм" in docx_resp.json()["extracted_text"]

    # 2. Текстовый PDF извлекается корректно.
    text_pdf = _make_text_pdf_bytes("Economist job description sums check")
    tpdf_resp = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={"file": ("jd.pdf", text_pdf, "application/pdf")},
        data={"position_code": "economist-training"},
    )
    assert tpdf_resp.status_code == 201
    assert tpdf_resp.json()["extraction_status"] == "ready"
    assert "Economist job description" in tpdf_resp.json()["extracted_text"]

    # 3. Битый PDF -> failed с видимой причиной.
    bad_pdf_resp = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={"file": ("broken.pdf", b"%PDF-broken-bytes", "application/pdf")},
        data={"position_code": "economist-training"},
    )
    assert bad_pdf_resp.status_code == 201
    assert bad_pdf_resp.json()["extraction_status"] == "failed"
    assert bad_pdf_resp.json()["extracted_text"] is None
    assert "PDF_INVALID" in bad_pdf_resp.json()["reason"]

    # 4. Скан PDF (без текстового слоя) -> unavailable -> 409 SOURCE_NOT_READY при утверждении -> транскрипция.
    scan_bytes = _make_blank_pdf_bytes()
    scan_resp = client.post(
        "/api/v1/sources",
        headers=auth_headers("hr"),
        files={"file": ("scan.pdf", scan_bytes, "application/pdf")},
        data={"position_code": "economist-training"},
    )
    assert scan_resp.status_code == 201
    scan_src = scan_resp.json()
    scan_id = scan_src["id"]
    assert scan_src["extraction_status"] == "unavailable"
    assert scan_src["extracted_text"] is None
    assert "PDF_NEEDS_REVIEW" in scan_src["reason"]

    # Черновик без цитат (team-строка), но ссылающийся на скан в sources -> при approve даст 409 SOURCE_NOT_READY.
    team_draft = {
        "schema_version": "requirement-draft/1.0",
        "position_code": "economist-training",
        "is_synthetic": False,
        "sources": [{"source_document_id": scan_id, "role": "job_description", "is_primary": True}],
        "formal_requirements": [],
        "competencies": [
            {
                "key": "scan.team",
                "code": "SCAN",
                "name": "Скан-критерий",
                "origin": "team",
                "note": "Черновик до транскрипции скана",
                "indicators": [
                    {
                        "key": "scan.team.ind",
                        "text": "Проверка смет",
                        "verification": "interview",
                        "origin": "team",
                        "note": "Ожидание транскрипции",
                    }
                ],
            }
        ],
    }
    d_resp = client.post(
        "/api/v1/drafts",
        headers=auth_headers("hr"),
        json={"position_code": "economist-training", "content": team_draft},
    )
    assert d_resp.status_code == 201
    draft_id = d_resp.json()["id"]
    assert client.post(
        f"/api/v1/drafts/{draft_id}/submit",
        headers=auth_headers("hr"),
        json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
    ).status_code == 200
    assert client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("department"),
        json={"expected_revision": 2, "result": "accepted", "note": "Принято"},
    ).status_code == 200
    not_ready_approve = client.post(
        f"/api/v1/drafts/{draft_id}/approve",
        headers=auth_headers("hr"),
        json={"expected_revision": 3, "approval_basis": "Нельзя до транскрипции"},
    )
    assert not_ready_approve.status_code == 409
    assert not_ready_approve.json()["error"]["code"] == "SOURCE_NOT_READY"

    # Ручная транскрипция увеличивает revision источника до 2 и сохраняет оригинал байтов.
    tr_resp = client.post(
        f"/api/v1/sources/{scan_id}/transcription",
        headers=auth_headers("hr"),
        json={
            "expected_revision": 1,
            "text": "Ручная транскрипция скана ДИ: проверка смет и расчётов.",
            "transcription_basis": "Расшифровано HR по оригиналу скана №12",
        },
    )
    assert tr_resp.status_code == 200
    assert tr_resp.json()["revision"] == 2
    assert tr_resp.json()["extraction_status"] == "ready"
    assert tr_resp.json()["text_origin"] == "manual_transcription"

    # Оригинальный файл PDF не изменился!
    orig = client.get(f"/api/v1/documents/{scan_id}/content", headers={"Authorization": "Bearer fixture:hr"})
    assert orig.status_code == 200
    assert orig.content == scan_bytes

    # Прежнее согласование было на source_revision=1 -> approve отклонён 409 INVALID_STATE.
    stale_source_approve = client.post(
        f"/api/v1/drafts/{draft_id}/approve",
        headers=auth_headers("hr"),
        json={"expected_revision": 3, "approval_basis": "Попытка без пересогласования"},
    )
    assert stale_source_approve.status_code == 409
    assert stale_source_approve.json()["error"]["code"] == "INVALID_STATE"

    # Повторное согласование на новой ревизии источника позволяет утвердить рабочий профиль.
    re_accept = client.post(
        f"/api/v1/drafts/{draft_id}/review",
        headers=auth_headers("department"),
        json={"expected_revision": 3, "result": "accepted", "note": "Согласовано после транскрипции"},
    )
    assert re_accept.status_code == 200
    assert re_accept.json()["accepted_source_revisions"] == {scan_id: 2}
    ok_approve = client.post(
        f"/api/v1/drafts/{draft_id}/approve",
        headers=auth_headers("hr"),
        json={"expected_revision": 4, "approval_basis": "Утверждено после ручного ввода скана"},
    )
    assert ok_approve.status_code == 201
    v1_profile = ok_approve.json()
    assert v1_profile["sources_snapshot"][0]["source_revision"] == 2

    # Последующая транскрипция до revision=3 не изменяет сохранённый снимок v1!
    tr2 = client.post(
        f"/api/v1/sources/{scan_id}/transcription",
        headers=auth_headers("hr"),
        json={
            "expected_revision": 2,
            "text": "Обновлённая ручная транскрипция v3.",
            "transcription_basis": "Уточнение скана",
        },
    )
    assert tr2.status_code == 200
    v1_again = client.get(f"/api/v1/profiles/{v1_profile['id']}", headers={"Authorization": "Bearer fixture:hr"})
    assert v1_again.status_code == 200
    assert v1_again.json()["sources_snapshot"][0]["source_revision"] == 2
    assert "проверка смет" in v1_again.json()["sources_snapshot"][0]["extracted_text"]


def test_quotes_idempotency_stale_revision_and_file_size_limit(make_settings, broker):
    settings = make_settings(file_max_bytes=512)
    run_alembic_upgrade(settings.database_url)
    app = create_app(settings, publisher=broker)
    with TestClient(app) as client:
        # Превышение FILE_MAX_BYTES -> 413 FILE_TOO_LARGE.
        big_resp = client.post(
            "/api/v1/sources",
            headers=auth_headers("hr"),
            files={"file": ("big.txt", b"x" * 513, "text/plain")},
            data={"position_code": "economist-training"},
        )
        assert big_resp.status_code == 413
        assert big_resp.json()["error"]["code"] == "FILE_TOO_LARGE"

        src = _upload_txt_source(client)
        src_id = src["id"]

        # Неверная цитата -> 422 SOURCE_MISMATCH, тот же Idempotency-Key можно переиспользовать после сбоя.
        reusable_key = str(uuid.uuid4())
        bad_content = _make_economist_draft(src_id)
        bad_content["formal_requirements"][0]["source_refs"][0]["quote"] = "Выдуманная цитата"
        mismatch = client.post(
            "/api/v1/drafts",
            headers=auth_headers("hr", idempotency_key=reusable_key),
            json={"position_code": "economist-training", "content": bad_content},
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["error"]["code"] == "SOURCE_MISMATCH"

        # Повтор с тем же ключом, но исправленным телом проходит, потому что 422 не зафиксировал ключ.
        good_content = _make_economist_draft(src_id)
        fixed = client.post(
            "/api/v1/drafts",
            headers=auth_headers("hr", idempotency_key=reusable_key),
            json={"position_code": "economist-training", "content": good_content},
        )
        assert fixed.status_code == 201
        assert "Idempotency-Replayed" not in fixed.headers
        draft_id = fixed.json()["id"]

        # Идемпотентный повтор POST /drafts с тем же ключом -> 201 + Idempotency-Replayed=true.
        replay = client.post(
            "/api/v1/drafts",
            headers=auth_headers("hr", idempotency_key=reusable_key),
            json={"position_code": "economist-training", "content": good_content},
        )
        assert replay.status_code == 201
        assert replay.headers.get("Idempotency-Replayed") == "true"
        assert replay.json()["id"] == draft_id

        # Тот же ключ с другим телом -> 409 IDEMPOTENCY_CONFLICT.
        changed_content = deepcopy(good_content)
        changed_content["note"] = "Другое тело"
        conflict = client.post(
            "/api/v1/drafts",
            headers=auth_headers("hr", idempotency_key=reusable_key),
            json={"position_code": "economist-training", "content": changed_content},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

        # Отсутствие Idempotency-Key -> 422.
        no_key = client.post(
            "/api/v1/positions",
            headers={"Authorization": "Bearer fixture:hr"},
            json={"code": "no-key", "title": "Test"},
        )
        assert no_key.status_code == 422
        assert no_key.json()["error"]["field"] == "Idempotency-Key"

        # Доводим до согласования и тестируем повтор approve vs stale expected_revision.
        client.post(
            f"/api/v1/drafts/{draft_id}/submit",
            headers=auth_headers("hr"),
            json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
        )
        client.post(
            f"/api/v1/drafts/{draft_id}/review",
            headers=auth_headers("department"),
            json={"expected_revision": 2, "result": "accepted", "note": "ок"},
        )

        # Старая ревизия с новым ключом -> 409 STALE_REVISION.
        stale = client.post(
            f"/api/v1/drafts/{draft_id}/approve",
            headers=auth_headers("hr"),
            json={"expected_revision": 2, "approval_basis": "Старая форма"},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "STALE_REVISION"

        # Успешный approve с конкретным ключом.
        approve_key = str(uuid.uuid4())
        ok_app = client.post(
            f"/api/v1/drafts/{draft_id}/approve",
            headers=auth_headers("hr", idempotency_key=approve_key),
            json={"expected_revision": 3, "approval_basis": "Утверждено"},
        )
        assert ok_app.status_code == 201

        # Повтор ТОГО ЖЕ ключа approve (хотя draft уже approved и revision стал 4) -> 201 replay!
        replay_app = client.post(
            f"/api/v1/drafts/{draft_id}/approve",
            headers=auth_headers("hr", idempotency_key=approve_key),
            json={"expected_revision": 3, "approval_basis": "Утверждено"},
        )
        assert replay_app.status_code == 201
        assert replay_app.headers.get("Idempotency-Replayed") == "true"
        assert replay_app.json()["id"] == ok_app.json()["id"]


def test_concurrent_approvals_serialize_without_two_current_profiles(env):
    _app, client, _settings, _broker = env
    src = _upload_txt_source(client)
    src_id = src["id"]

    draft_ids = []
    for idx in range(2):
        content = _make_economist_draft(src_id, extra_note=f"Параллельный черновик {idx}")
        d = client.post(
            "/api/v1/drafts",
            headers=auth_headers("hr"),
            json={"position_code": "economist-training", "content": content},
        ).json()
        client.post(
            f"/api/v1/drafts/{d['id']}/submit",
            headers=auth_headers("hr"),
            json={"expected_revision": 1, "reviewer_actor_id": ACTOR_DEPT_1},
        )
        client.post(
            f"/api/v1/drafts/{d['id']}/review",
            headers=auth_headers("department"),
            json={"expected_revision": 2, "result": "accepted", "note": "Готов"},
        )
        draft_ids.append(d["id"])

    barrier = Barrier(2)

    def approve_one(did: str):
        barrier.wait(timeout=5)
        return client.post(
            f"/api/v1/drafts/{did}/approve",
            headers=auth_headers("hr"),
            json={"expected_revision": 3, "approval_basis": f"Параллельное утверждение {did}"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve_one, draft_ids))

    assert [r.status_code for r in responses] == [201, 201]
    versions = sorted(r.json()["version"] for r in responses)
    assert versions == [1, 2]

    # Проверяем, что один current, а второй стал историческим.
    p0 = client.get(f"/api/v1/profiles/{responses[0].json()['id']}", headers={"Authorization": "Bearer fixture:hr"}).json()
    p1 = client.get(f"/api/v1/profiles/{responses[1].json()['id']}", headers={"Authorization": "Bearer fixture:hr"}).json()
    assert sorted([p0["is_current"], p1["is_current"]]) == [False, True]
    current = client.get(
        "/api/v1/positions/economist-training/approved-profile?contour=training",
        headers={"Authorization": "Bearer fixture:hr"},
    ).json()
    assert current["version"] == 2
    assert current["is_current"] is True
