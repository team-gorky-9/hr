"""One HTTP integration path through both real sources, without external infrastructure."""
import json
from dataclasses import replace
from time import perf_counter
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_interaction_legacy import legacy_scenario
from hiring.api import create_app
from hiring.auth import fixture_actors
from hiring.config import Settings
from hiring.models import Base, CandidateRequest


def test_two_sources_through_real_http_routes(tmp_path, monkeypatch):
    with legacy_scenario(monkeypatch) as legacy:
        actors = fixture_actors(Settings())
        org = str(actors["hr"].organization_id)
        monkeypatch.setenv("INTERACTION_ORGANIZATION_ID", org)
        mapping_file = tmp_path / "mapping.json"
        mappings = []
        for name, user in [("hr", legacy.hr), ("department", legacy.dept)]:
            actor = actors[name]
            grant = actor.grants[0]
            mappings.append({"issuer": "fixture", "actor_id": str(actor.actor_id), "organization_id": org,
                             "contour": "training", "instance_id": "training-legacy",
                             "legacy_user_id": str(user.id), "legacy_login": user.login, "legacy_role": str(user.role),
                             "scope_type": grant.scope_type, "scope_id": str(grant.scope_id), "active": True, "revision": 1})
        mapping_file.write_text(json.dumps({"mappings": mappings}), encoding="utf-8")
        settings = replace(Settings(), database_url="sqlite:///" + (tmp_path / "portal.db").as_posix(),
                           interaction_enabled=True, interaction_mapping_file=mapping_file,
                           interaction_cursor_secret="test-cursor-secret", interaction_gateway_key="test-gateway-secret",
                           interaction_organization_id=org, interaction_legacy_url="http://legacy")
        app = create_app(settings)
        Base.metadata.create_all(app.state.engine)
        app.state.interaction_window.transport = httpx.ASGITransport(app=legacy.app)
        with Session(app.state.engine) as session:
            request = CandidateRequest(organization_id=actors["candidate"].organization_id,
                                       author_actor_id=actors["candidate"].actor_id,
                                       status="submitted", message="PRIVATE TEXT", contact={"value": "PRIVATE CONTACT"})
            session.add(request)
            session.commit()
            request_id = str(request.id)
        samples = []
        with TestClient(app) as client:
            def call(method, path, actor="hr", **kwargs):
                # Spoofed browser headers must never influence the source actor.
                response = client.request(method, "/api/v1/" + path,
                    headers={"Authorization": f"Bearer fixture:{actor}", "X-User-Login": "admin_demo",
                             "X-Interaction-User-Id": str(uuid4()), "X-Interaction-Gateway-Key": "spoofed"}, **kwargs)
                assert response.status_code < 400, response.text
                return response.json()
            def window(actor="hr", **params):
                start = perf_counter()
                result = call("GET", "interaction-window", actor, params=params)
                samples.append((perf_counter() - start, len(json.dumps(result, ensure_ascii=False).encode())))
                assert "PRIVATE" not in json.dumps(result)
                return result
            assert client.get("/api/v1/interaction-window").status_code == 401
            prefix = f"candidate-requests/{request_id}"
            q = call("POST", prefix + "/information-request", json={"expected_revision": 1,
                     "public_message": "Add evidence", "requested_items": ["Experience"]})
            assert window("candidate")["items"][0]["relation"] == "needs_my_action"
            assert window("candidate2")["items"] == []
            messages = call("GET", prefix + "/messages", "candidate")
            message = messages["items"][0]
            call("POST", prefix + f"/messages/{message['id']}/read", "candidate")
            assert window("candidate")["items"][0]["relation"] == "needs_my_action"
            answer = call("POST", prefix + "/addendum", "candidate", json={
                "expected_revision": q["revision"], "information_request_ref": q["information_request_ref"], "text": "Evidence"})
            assert any(i["reason_code"] == "addendum_requires_review" for i in window()["items"])
            call("POST", prefix + "/ready", json={"expected_revision": answer["revision"], "review_basis": "Evidence checked"})
            gateway = "interaction-window/legacy/"
            application = str(legacy.application.id)
            h1, h2 = [str(a.id) for a in legacy.attempts]
            feedback = call("POST", gateway + f"applications/{application}/feedback", "department", json={
                "attempt_id": h1, "outcome": "fit", "request_id": str(uuid4())})["feedback"]
            assert legacy.attempts[1].status == "awaiting_response"
            assert legacy.application.current_stage_code == "sent_to_department"
            review = {"feedbacks": [{"attempt_id": h1, "feedback_id": feedback["feedback_id"], "revision": 1}],
                      "expected_seq": 1, "request_id": str(uuid4()), "result": "continue_waiting", "basis": "Keep H2 open"}
            first = call("POST", gateway + f"applications/{application}/feedback-reviews", json=review)
            assert call("POST", gateway + f"applications/{application}/feedback-reviews", json=review) == first
            combined = window()
            assert combined["completeness"] == "complete" and {s["source"] for s in combined["sources"]} == {"hiring.portal", "legacy"}
            for item in combined["items"]:
                assert {"state", "reason_code", "source_version", "basis_ref", "observed_at", "occurred_at", "related_ref"} <= item.keys()
                assert {"source", "kind", "id"} <= item["subject_ref"].keys()
                assert item["responsible"]["kind"] in {"self", "actor", "role_scope", "external"}
                assert all("availability" in action for action in item["actions"])
            first_page = window(page_size=1)
            cursor = first_page["sources"][1]["next_cursor"]
            assert cursor
            window(page_size=1, legacy_cursor=cursor)
            call("POST", gateway + f"handoffs/{h1}/revoke-access", json={
                "expected_assignment_revision": 1, "request_id": str(uuid4()), "reason": "Reassigned"})
            response = client.get("/api/v1/" + gateway + f"handoffs/{h1}", headers={"Authorization": "Bearer fixture:department"})
            assert response.status_code == 403
            remaining = window("department")
            assert all(i["expectation_ref"].get("attempt_id") != h1 for i in remaining["items"])
            assert any(i["expectation_ref"].get("attempt_id") == h2 for i in remaining["items"])
            # Known real-data IDs cannot bypass the training gate through an old route.
            from app.db.models import Candidate
            candidate = legacy.session.get(Candidate, legacy.application.candidate_id)
            candidate.is_synthetic = False
            legacy.session.commit()
            forbidden = client.get("/api/v1/" + gateway + f"applications/{application}/history",
                                   headers={"Authorization": "Bearer fixture:hr"})
            assert forbidden.status_code == 403
            assert client.get("/api/v1/interaction-window/legacy/health",
                              headers={"Authorization": "Bearer fixture:hr"}).status_code == 404
            assert client.get("/api/v1/interaction-window", headers={"Authorization": "Bearer fixture:hr"}).headers["cache-control"] == "no-store"
        app.state.engine.dispose()
        print(f"window_measurement: reads={len(samples)}, max_ms={max(t for t, _ in samples)*1000:.1f}, max_bytes={max(b for _, b in samples)}")
