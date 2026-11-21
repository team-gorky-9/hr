"""A single synthetic case from an incomplete submission to confirmed execution."""
import json
import os
from pathlib import Path

from .conftest import actor_id, assign, get_case, upload
from .test_5b import confirm, review
from .test_5d import close, execute, executor


def test_support_demo(server):
    api = server
    requests = []
    original_call = api.call

    def recorded_call(method, path, login="employee", status=200, **kwargs):
        # Persist only public fixture logins and synthetic bodies, never headers/tokens.
        inputs = {key: value for key, value in kwargs.items() if key != "files"}
        if "files" in kwargs:
            filename, content, content_type = kwargs["files"]["file"]
            inputs["file"] = {"name": filename, "text": content.decode("utf-8"), "content_type": content_type}
        requests.append({"actor": login, "method": method, "path": path, "input": inputs})
        return original_call(method, path, login, status, **kwargs)

    api.call = recorded_call
    rule = api.call("GET", "/rules")[0]
    case = api.call("POST", "/cases", status=201, json={
        "rule_version_id": rule["id"], "statement": "Учебное заявление DEMO-6B, без реальных персональных данных",
    })
    ident = case["id"]
    application_doc = upload(api, case, content=b"synthetic: application DEMO-6B")
    case = get_case(api, ident)
    case = api.call("POST", f"/cases/{ident}/submit", json={"expected_revision": case["revision"]})
    case = confirm(api, assign(api, case))
    case = api.call("POST", f"/cases/{ident}/completeness", "specialist", json={
        "expected_revision": case["revision"],
        "items": [
            {"key": "application", "result": "present", "document_id": application_doc["id"], "reason": ""},
            {"key": "evidence", "result": "missing", "document_id": None, "reason": "Нет учебного приложения"},
        ],
        "public_message": "Добавьте учебное подтверждающее приложение",
    })
    assert case["status"] == "needs_information"
    extra_doc = upload(api, get_case(api, ident), "evidence", b"synthetic: additional evidence DEMO-6B")
    case = get_case(api, ident)
    case = api.call("POST", f"/cases/{ident}/addenda", json={
        "expected_revision": case["revision"], "text": "Дополняю отсутствующее учебное приложение",
        "document_ids": [extra_doc["id"]],
    })
    assert len(case["submissions"]) == 2
    assert case["submissions"][0]["document_ids"] == [application_doc["id"]]
    assert set(case["submissions"][1]["document_ids"]) == {application_doc["id"], extra_doc["id"]}
    case = review(api, get_case(api, ident, "specialist"))
    assert case["status"] == "ready_for_review"
    case = api.call("POST", f"/cases/{ident}/decision", "secretary", json={
        "expected_revision": case["revision"], "outcome": "approved",
        "public_explanation": "Учебный внешний итог: помощь одобрена. Исполнение подтверждается отдельно.",
        "source_reference": "INTERNAL synthetic external protocol DEMO-6B",
        "source_author": "Учебная внешняя комиссия", "decided_on": "2026-11-21",
        "recording_basis": "INTERNAL manual registration of synthetic external decision",
    })
    decision = case["decisions"][-1]
    assert decision["recorded_by"] == actor_id("secretary")
    assert decision["source_author"] == "Учебная внешняя комиссия"
    extract = api.call("GET", f"/cases/{ident}/extract")
    assert extract["case_id"] == ident and extract["outcome"] == "approved"
    assert "INTERNAL" not in json.dumps(extract)
    assert get_case(api, ident)["execution"]["status"] == "unknown"
    for path in (f"/cases/{ident}", f"/cases/{ident}/extract"):
        api.call("GET", path, "employee2", status=404)
    case = execute(api, executor(api, case), "unknown")
    assert get_case(api, ident)["execution"]["status"] == "unknown"
    # execute() records a synthetic external accounting source and a distinct registrar.
    case = execute(api, case, "confirmed")
    case = close(api, case)
    assert case["status"] == "closed" and case["execution"]["status"] == "confirmed"
    personal = get_case(api, ident)
    assert "INTERNAL" not in json.dumps(personal)
    assert len(case["executions"]) == 2
    api.restart()
    assert get_case(api, ident) == personal
    assert api.call("GET", f"/cases/{ident}/extract") == extract
    assert api.call("GET", f"/cases/{ident}/documents/{application_doc['id']}/content").content == b"synthetic: application DEMO-6B"
    api.call("GET", f"/cases/{ident}/extract", "employee2", status=404)
    history = api.call("GET", f"/cases/{ident}/history")
    assert "INTERNAL" not in json.dumps(history)
    ids = {"case": ident, "application_document": application_doc["id"], "additional_document": extra_doc["id"],
           "decision": decision["id"], "extract": extract["id"]}
    report_dir = os.environ.get("WAVE6_REPORT_DIR")
    if report_dir:
        target = Path(report_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "wave-6-support-examples.json").write_text(json.dumps({
            "is_synthetic": True, "source": "support-training-v1 / DEMO-6B",
            "ids": ids, "restart_verified": True, "requests": requests, "trace": api.trace,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(ids, ensure_ascii=False))
