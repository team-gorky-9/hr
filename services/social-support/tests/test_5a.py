from .conftest import actor_id, assign, get_case, upload

def test_private_submission_and_durable_originals(server):
    api = server
    rule = api.call("GET", "/rules")[0]
    assert rule["is_synthetic"]
    case = api.call("POST", "/cases", status=201,
                   json={"rule_version_id": rule["id"], "statement": "Учебное обращение"})
    ident = case["id"]
    for login in ("employee2", "specialist", "secretary", "coordinator", "other_org"):
        api.call("GET", f"/cases/{ident}", login, status=404)
        assert api.call("GET", "/cases", login) == []
    first = upload(api, case)
    case = get_case(api, ident)
    second = upload(api, case, "evidence")
    case = get_case(api, ident)
    assert len(case["documents"]) == 2
    api.call("POST", f"/cases/{ident}/documents", status=422,
             data={"expected_revision": case["revision"], "item_key": "application"},
             files={"file": ("empty.txt", b"", "text/plain")})
    assert get_case(api, ident)["revision"] == case["revision"]
    case = api.call("POST", f"/cases/{ident}/submit", json={"expected_revision": case["revision"]})
    assert case["status"] == "submitted" and case["number"]
    assert set(case["submissions"][0]["document_ids"]) == {first["id"], second["id"]}
    api.call("POST", f"/cases/{ident}/submit", status=409, json={"expected_revision": 3})
    queue = api.call("GET", "/cases", "coordinator")[0]
    assert "statement" not in queue and "documents" not in queue
    case = assign(api, case)
    assert len(case["documents"]) == 2
    original = f'/cases/{ident}/documents/{first["id"]}/content'
    for login in ("employee2", "manager", "coordinator", "other_org"):
        api.call("GET", original, login, status=404)
    assert api.call("GET", original).content == b"synthetic attachment"
    internal = upload(api, case, "internal", b"internal protocol", "secretary", visibility="internal")
    api.call("GET", f'/cases/{ident}/documents/{internal["id"]}/content', status=404)
    assert len(get_case(api, ident)["documents"]) == 2
    api.restart()
    assert api.call("GET", original, "specialist").content == b"synthetic attachment"
    assert get_case(api, ident)["number"] == case["number"]
    api.export("wave-5a-support")
