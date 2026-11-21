"""Run against a dedicated server with the standard search demo loaded."""
import json
import sys
import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18400/api/v1"
with httpx.Client(base_url=base, headers={"X-User-Login": "hr_demo"}, timeout=15) as client:
    def check(method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response.json()
    search = check("POST", "/search/candidates", json={"query":"BPMN", "contour":"training"})
    candidate = next(item for item in search["items"] if item["candidate_code"] == "search-9001")
    used = {item["vacancy_id"] for item in candidate["applications"]}
    vacancy = next(item for item in check("GET", "/vacancies?contour=training")["items"] if item["vacancy_id"] not in used)
    source = check("GET", "/candidate-texts/" + candidate["evidence"]["candidate_text_id"])
    assert candidate["evidence"]["fragment"] in source["text"]
    entry = check("POST", "/reserve", expected=201, json={
        "candidate_id":candidate["candidate_id"], "position_id":vacancy["position_id"],
        "reason":"Учебная проверка повторного рассмотрения", "contact_basis":"Учебное согласие на повторный контакт",
    })["entry"]
    payload = dict(candidate_id=candidate["candidate_id"], vacancy_id=vacancy["vacancy_id"],
                   reserve_id=entry["reserve_id"], contour="training", confirmation="Учебный звонок, кандидат согласился.")
    rejected = client.post("/archive/reconsiderations", json={**payload, "confirmation":" "})
    assert rejected.status_code == 422
    forbidden = client.post("/archive/reconsiderations", headers={"X-User-Login":"dept_demo"}, json=payload)
    assert forbidden.status_code == 403
    created = check("POST", "/archive/reconsiderations", expected=201, json=payload)
    replay = check("POST", "/archive/reconsiderations", json=payload)
    assert created["application_id"] == replay["application_id"] and not replay["created"]
    history = check("GET", "/applications/" + created["application_id"] + "/history")
    assert history["stage"]["code"] == "new" and len(history["items"]) == 1
    assert "Учебный звонок" in history["items"][0]["comment"]
    assert history["items"][0]["actor"]["login"] == "hr_demo"
    for old in candidate["applications"]:
        assert check("GET", "/applications/" + old["application_id"] + "/history")["stage"]["code"] == old["stage_code"]
    print(json.dumps({"candidate":candidate["candidate_code"], "vacancy":vacancy["title"], "created":created, "replay":replay, "checks":"source, contact basis, explicit confirmation, 403, repeat, history, old applications unchanged"}, ensure_ascii=False))
