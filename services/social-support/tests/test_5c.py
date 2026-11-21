from .conftest import actor_id, assign, get_case
from .test_5b import ready, review

def decision_body(case, outcome="approved"):
    return {"expected_revision": case["revision"], "outcome": outcome,
            "public_explanation": "Учебное решение: помощь одобрена" if outcome == "approved" else "Учебный отказ: основание не подтверждено",
            "source_reference": "INTERNAL synthetic protocol for several cases",
            "source_author": "Учебная комиссия",
            "decided_on": "2026-11-21", "recording_basis": "INTERNAL registrar authority"}

def decide(api, case, outcome="approved"):
    return api.call("POST", f'/cases/{case["id"]}/decision', "secretary", json=decision_body(case, outcome))

def test_decision_extract_correction_and_self_recusal(server):
    api = server
    case = ready(api)
    ident = case["id"]
    case = decide(api, case)
    assert case["decisions"][-1]["source_author"] == "Учебная комиссия"
    assert case["decisions"][-1]["recorded_by"] == actor_id("secretary")
    extract = api.call("GET", f"/cases/{ident}/extract")
    assert extract["outcome"] == "approved" and extract["version"] == 1
    for path in (f"/cases/{ident}", f"/cases/{ident}/history", f"/cases/{ident}/extract"):
        api.call("GET", path, "manager", status=404)
        api.call("GET", path, "employee2", status=404)
        assert "INTERNAL" not in str(api.call("GET", path))
    body = decision_body(case, "declined") | {"correction_reason": "Исправлен ошибочно внесённый исход"}
    case = api.call("POST", f"/cases/{ident}/decision-corrections", "secretary", json=body)
    assert len(case["decisions"]) == 2 and case["decisions"][0]["outcome"] == "approved"
    assert api.call("GET", f"/cases/{ident}/extract")["version"] == 2
    api.call("POST", f"/cases/{ident}/decision-corrections", "secretary", status=409, json=body)

    # A secretary can apply, but cannot register a decision on their own application.
    own = ready(api, login="secretary", secretary="secretary")
    api.call("POST", f'/cases/{own["id"]}/decision', "secretary", status=404, json=decision_body(own))
    own = assign(api, own, secretary="secretary2")
    own = api.call("POST", f'/cases/{own["id"]}/decision', "secretary2", json=decision_body(own, "declined"))
    assert own["decisions"][-1]["recorded_by"] == actor_id("secretary2")

    more = ready(api, "employee2")
    more = decide(api, more, "needs_information")
    assert more["status"] == "needs_information"
    api.call("POST", f'/cases/{more["id"]}/decision', "secretary", status=409, json=decision_body(more))
    api.restart()
    assert api.call("GET", f"/cases/{ident}/extract")["outcome"] == "declined"
    assert api.call("GET", f'/cases/{own["id"]}/extract', "secretary")["outcome"] == "declined"
    api.export("wave-5c-support")
