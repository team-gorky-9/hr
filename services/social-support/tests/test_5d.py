from .conftest import actor_id, get_case, submitted
from .test_5b import ready
from .test_5c import decide, decision_body

def executor(api, case):
    api.call("POST", f'/cases/{case["id"]}/executor-assignment', "coordinator",
             json={"expected_revision": case["revision"], "executor_actor_id": actor_id("executor"),
                   "assignment_basis": "synthetic: accounting registrar"})
    return get_case(api, case["id"], "executor")

def execution_body(case, status):
    return {"expected_revision": case["revision"], "status": status,
            "source_reference": "INTERNAL synthetic accounting registry",
            "source_author": "Учебный регистратор", "occurred_on": "2026-11-21" if status != "unknown" else None,
            "note": "INTERNAL evidence note"}

def execute(api, case, status):
    return api.call("POST", f'/cases/{case["id"]}/execution', "executor", json=execution_body(case, status))

def close(api, case):
    return api.call("POST", f'/cases/{case["id"]}/close', "specialist",
                    json={"expected_revision": case["revision"], "reason": "Явное учебное основание завершения"})

def test_execution_is_not_approval_and_closure_preserves_unknown(server):
    api = server
    case = decide(api, ready(api))
    ident = case["id"]
    assert get_case(api, ident)["execution"]["status"] == "unknown"
    api.call("POST", f"/cases/{ident}/execution", "executor", status=404, json=execution_body(case, "confirmed"))
    api.call("POST", f"/cases/{ident}/withdraw", status=409,
             json={"expected_revision": case["revision"], "reason": "После решения нельзя"})
    case = executor(api, case)
    assert "statement" not in case and "documents" not in case and "submissions" not in case
    full_case = get_case(api, ident, "specialist")
    doc = full_case["documents"][0]["id"]
    api.call("GET", f"/cases/{ident}/documents/{doc}/content", "executor", status=404)
    case = execute(api, case, "unknown")
    assert get_case(api, ident)["execution"]["status"] == "unknown"
    case = execute(api, case, "failed")
    assert get_case(api, ident)["execution"]["status"] == "failed"
    case = execute(api, case, "confirmed")
    case = close(api, case)
    assert case["status"] == "closed" and case["execution"]["status"] == "confirmed"
    assert len(case["executions"]) == 3
    assert "INTERNAL" not in str(get_case(api, ident))
    execution_history = api.call("GET", f"/cases/{ident}/history", "executor")
    assert all(e["action"] in {"execution_recorded", "decision_recorded", "decision_corrected", "closed"} for e in execution_history)

    unknown = decide(api, ready(api, "employee2"))
    unknown = close(api, unknown)
    assert unknown["execution"]["status"] == "unknown"
    assert get_case(api, unknown["id"], "employee2")["status"] == "closed"

    declined = decide(api, ready(api), "declined")
    declined = executor(api, declined)
    api.call("POST", f'/cases/{declined["id"]}/execution', "executor", status=409,
             json=execution_body(declined, "confirmed"))
    declined = close(api, declined)
    assert declined["status"] == "closed"

    corrected = decide(api, ready(api))
    corrected = execute(api, executor(api, corrected), "confirmed")
    full = get_case(api, corrected["id"], "secretary")
    body = decision_body(full) | {"correction_reason": "Исправлены условия внешнего решения"}
    corrected = api.call("POST", f'/cases/{full["id"]}/decision-corrections', "secretary", json=body)
    assert corrected["execution"]["status"] == "unknown"
    assert len(corrected["executions"]) == 1

    withdrawn = submitted(api)
    withdrawn = api.call("POST", f'/cases/{withdrawn["id"]}/withdraw',
                         json={"expected_revision": withdrawn["revision"], "reason": "Учебный отзыв"})
    assert withdrawn["status"] == "withdrawn"
    rule = api.call("GET", "/rules")[0]
    draft = api.call("POST", "/cases", status=201,
                     json={"rule_version_id": rule["id"], "statement": "Личный отозванный черновик"})
    api.call("POST", f'/cases/{draft["id"]}/withdraw',
             json={"expected_revision": draft["revision"], "reason": "Не буду подавать"})
    assert draft["id"] not in {c["id"] for c in api.call("GET", "/cases", "coordinator")}
    api.restart()
    assert get_case(api, ident)["status"] == "closed"
    assert get_case(api, ident)["execution"]["status"] == "confirmed"
    api.export("wave-5d-support")
