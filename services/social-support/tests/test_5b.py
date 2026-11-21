from .conftest import assign, get_case, submitted, upload

def items(case, result="present"):
    docs = {d["id"]: d for d in case["documents"]}
    return [{"key": docs[d]["item_key"], "document_id": d,
             "result": result if docs[d]["item_key"] == "evidence" else "present",
             "reason": "Нужен читаемый оригинал" if result != "present" else ""}
            for d in case["submissions"][-1]["document_ids"]]

def confirm(api, case):
    return api.call("POST", f'/cases/{case["id"]}/staff-confirmation', "specialist",
                    json={"expected_revision": case["revision"], "state": "confirmed",
                          "source_reference": "synthetic: workforce training v1"})

def review(api, case, result="present"):
    return api.call("POST", f'/cases/{case["id"]}/completeness', "specialist",
                    json={"expected_revision": case["revision"], "items": items(case, result),
                          "public_message": "Добавьте читаемый документ" if result != "present" else "Комплект проверен"})

def ready(api, login="employee", secretary="secretary"):
    return review(api, confirm(api, assign(api, submitted(api, login), secretary)))

def test_new_submission_requires_new_review(server):
    api = server
    case = assign(api, submitted(api))
    ident = case["id"]
    case = review(api, case)
    assert case["status"] == "submitted"  # employee role does not prove staff status
    case = confirm(api, case)
    case = review(api, case, "unreadable")
    assert case["status"] == "needs_information"
    old_revision = case["revision"]
    old_items = items(case)
    first_id = case["submissions"][-1]["document_ids"][1]
    replacement = upload(api, get_case(api, ident), "evidence", b"new readable synthetic evidence")
    case = get_case(api, ident)
    case = api.call("POST", f"/cases/{ident}/addenda",
                   json={"expected_revision": case["revision"], "text": "Новый читаемый скан",
                         "document_ids": [replacement["id"]]})
    assert case["status"] == "submitted" and len(case["submissions"]) == 2
    api.call("POST", f"/cases/{ident}/completeness", "specialist", status=409,
             json={"expected_revision": old_revision, "items": old_items, "public_message": "Старая форма"})
    api.call("POST", f"/cases/{ident}/completeness", "specialist", status=422,
             json={"expected_revision": case["revision"], "items": old_items, "public_message": "Старый файл"})
    api.call("POST", f"/cases/{ident}/staff-confirmation", "employee2", status=404,
             json={"expected_revision": case["revision"], "state": "confirmed", "source_reference": "spoof"})
    case = review(api, get_case(api, ident, "specialist"))
    assert case["status"] == "ready_for_review"
    assert [c["submission_revision"] for c in case["checklists"]] == [1, 1, 2]
    assert api.call("GET", f"/cases/{ident}/documents/{first_id}/content").content == b"synthetic attachment"
    api.restart()
    assert get_case(api, ident)["status"] == "ready_for_review"
    history = api.call("GET", f"/cases/{ident}/history")
    assert all("internal" not in e for e in history)
    assert any(e["public"].get("message") == "Добавьте читаемый документ" for e in history)
    api.export("wave-5b-support")
