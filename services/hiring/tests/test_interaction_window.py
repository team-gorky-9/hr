"""Small compositor boundary checks; source domain scenarios live beside their owners."""
import asyncio
import json
from dataclasses import replace
from uuid import UUID

import httpx
import pytest

from hiring.auth import fixture_actors
from hiring.config import Settings
from hiring.errors import Problem


def test_explicit_identity_partial_failure_and_closed_proxy(tmp_path, monkeypatch):
    from hiring.interaction_window import InteractionWindow
    base = Settings()
    actors = fixture_actors(base)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"mappings": [{
        "issuer": "fixture", "actor_id": str(actors["hr"].actor_id),
        "organization_id": str(actors["hr"].organization_id), "contour": "training",
        "instance_id": "training-legacy", "legacy_login": "hr_demo", "legacy_role": "hr",
        "legacy_user_id": str(UUID(int=10)),
        "scope_type": "organization", "scope_id": str(actors["hr"].organization_id),
        "revision": 1, "active": True,
    }]}), encoding="utf-8")
    settings = replace(base, interaction_enabled=True, interaction_mapping_file=mapping,
                       interaction_cursor_secret="test-secret", interaction_gateway_key="gateway-secret",
                       interaction_legacy_url="http://legacy", interaction_organization_id=str(actors["hr"].organization_id))
    requests = []
    broken = False
    def remote(request):
        requests.append(request)
        assert request.headers["X-User-Login"] == "hr_demo"
        assert request.headers["X-Interaction-Gateway-Key"] == "gateway-secret"
        assert "Authorization" not in request.headers
        if broken:
            raise httpx.ConnectError("private address must not leak")
        envelope = {"actor": {"login": "hr_demo", "role": "hr", "user_id": str(UUID(int=10))},
                    "organization_id": settings.interaction_organization_id,
                    "instance_id": "training-legacy", "contour": "training", "gateway_enforced": True}
        return httpx.Response(200, json=envelope | {"items": [], "source": {
            "source": "legacy", "status": "ok", "observed_at": "2026-11-21T00:00:00+00:00",
            "source_as_of": None, "next_cursor": None, "coverage": "complete"}})
    window = InteractionWindow(settings, None, transport=httpx.MockTransport(remote))
    def portal(actor, **filters):
        return {"source": "hiring.portal", "status": "ok", "observed_at": "2026-11-21T00:00:00+00:00",
                "source_as_of": None, "next_cursor": None, "coverage": "complete", "items": []}
    monkeypatch.setattr(window, "portal_read", portal)
    async def scenario():
        nonlocal broken
        body, status = await window.read(actors["hr"])
        assert status == 200 and body["completeness"] == "complete"
        broken = True
        body, status = await window.read(actors["hr"])
        assert status == 200 and body["completeness"] == "partial"
        assert "private address" not in json.dumps(body)
        before = len(requests)
        body, status = await window.read(actors["candidate"])
        assert len(requests) == before and body["sources"][1]["status"] == "not_applicable"
        for path in ["admin/users", "../health", "handoffs/not-a-uuid"]:
            with pytest.raises(Problem) as error:
                await window.proxy(actors["hr"], "GET", path, b"")
            assert error.value.status == 404
        mapping.write_text('{"mappings": []}', encoding="utf-8")
        body, status = await window.read(actors["hr"])
        assert body["sources"][1]["status"] == "not_linked"
        with pytest.raises(Problem) as denied:
            await window.proxy(actors["hr"], "GET", f"handoffs/{UUID(int=1)}", b"")
        assert denied.value.status == 403
        def unavailable(*args, **kwargs):
            raise RuntimeError("private database detail")
        monkeypatch.setattr(window, "portal_read", unavailable)
        body, status = await window.read(actors["candidate"])
        assert status == 503 and body["items"] == []
    asyncio.run(scenario())
