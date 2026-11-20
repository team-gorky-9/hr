"""Проверка реальных HTTP-ответов учебного поиска на свежей базе load-demo."""
import argparse

import httpx

PATH = "/api/v1/search/candidates"


def check(client: httpx.Client, *, probe_semantic: bool) -> dict:
    denied = client.post(PATH, json={"query": "FastAPI"})
    assert denied.status_code == 401 and denied.json()["error"]["code"] == "SEARCH_AUTH_REQUIRED"
    invalid = client.post(PATH, json={"contour": "training", "query": "  "})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    def post(**payload) -> dict:
        response = client.post(PATH, json={"contour": "training", **payload})
        response.raise_for_status()
        assert response.headers["cache-control"] == "private, no-store"
        return response.json()

    result = post(query="анализ и согласование требований к ИС")
    match = next(item for item in result["items"] if item["candidate_code"] == "search-9001")
    evidence = match["evidence"]
    assert len([item for item in result["items"] if item["candidate_code"] == "search-9001"]) == 1
    text_response = client.get(f"/api/v1/candidate-texts/{evidence['candidate_text_id']}")
    text_response.raise_for_status()
    text = text_response.json()["text"]
    assert evidence["fragment"] == text[evidence["start_offset"]:evidence["end_offset"]]
    encoded = text.encode("utf-16-le")
    fragment = encoded[2 * evidence["utf16_start"]:2 * evidence["utf16_end"]].decode("utf-16-le")
    assert fragment == evidence["fragment"] and evidence["utf16_start"] > evidence["start_offset"]
    assert sorted(app["source"] for app in match["applications"]) == ["history", "manual", "response"]
    assert len([app for app in match["applications"] if app["is_active"]]) == 2
    exact = post(filters={"required_terms": ["44 - ФЗ", "ЕИС"]})
    exact_hit, = exact["items"]
    assert exact_hit["candidate_code"] == "search-9002" and exact_hit["match_kind"] == "exact"
    assert exact_hit["score"] is None and "44‑ФЗ" in exact_hit["evidence"]["fragment"]
    filters = post(filters={"skills": ["Python", "FastAPI"], "in_reserve": True})
    structured, = filters["items"]
    assert structured["candidate_code"] == "search-9006" and structured["evidence"] is None
    empty = post(query="монтаж телескопа", filters={"required_terms": ["коронограф"]})
    assert not empty["items"]
    summary = {"mode": result["mode"], "semantic_status": result["semantic_status"],
               "text_id": evidence["candidate_text_id"], "matched": match["candidate_code"],
               "exact": exact_hit["candidate_code"], "filters": structured["candidate_code"],
               "empty": True, "bad_request": 422, "denied": 401}
    if probe_semantic:
        probe = post(query="электронная маршрутизация жалоб населения", limit=50)
        matches = [item for item in probe["items"] if item["match_kind"] in ("semantic", "hybrid")]
        assert probe["mode"] == "hybrid" and probe["semantic_status"] == "ready"
        assert any(item["candidate_code"] == "search-9013" for item in matches), (
            "Измерительный запрос не дошёл до search-9013. Проверьте индексацию и порог смоука.",
            [item["candidate_code"] for item in matches],
        )
        summary["semantic_probe"] = "search-9013"
    return summary


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--probe-semantic", action="store_true")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        print(json.dumps(check(client, probe_semantic=args.probe_semantic), ensure_ascii=False))
