"""Bounded composition, explicit identity binding and a closed legacy command gateway.

No expectations are stored here. No caller headers, URL, login or organization are forwarded.
The mapping is reread on every request so removing a binding revokes old window links.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import threading
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from hiring.errors import Problem
from hiring.interaction_portal import read_portal_source

RELATIONS = {"needs_my_action", "waiting_on_other", "completed", "information"}
UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
ROUTES = {
    "GET": [rf"handoffs/{UUID_PATTERN}", rf"applications/{UUID_PATTERN}",
            rf"applications/{UUID_PATTERN}/(?:handoff-summary|handoffs|feedback|history)",
            rf"candidate-texts/{UUID_PATTERN}", r"references/(?:stages|rejection-reasons)"],
    "POST": [rf"applications/{UUID_PATTERN}/(?:handoffs|feedback|stage|feedback-reviews)",
             rf"handoffs/{UUID_PATTERN}/revoke-access",
             rf"applications/{UUID_PATTERN}/handoffs/{UUID_PATTERN}/deadline"],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def source_state(source, status, error_code=None):
    return {"source": source, "status": status, "observed_at": now(), "source_as_of": None,
            "next_cursor": None, "coverage": "unknown", "error_code": error_code}


class SourceFailure(Exception):
    def __init__(self, code="SOURCE_UNAVAILABLE", status="unavailable"):
        self.code, self.status = code, status


class InteractionWindow:
    def __init__(self, settings, engine, *, transport=None):
        self.settings, self.engine, self.transport = settings, engine, transport
        self.portal_slots = threading.BoundedSemaphore(4)

    def mapping(self, actor):
        s = self.settings
        if actor.is_candidate() or str(actor.organization_id) != s.interaction_organization_id:
            return None
        try:
            rows = json.loads(s.interaction_mapping_file.read_text(encoding="utf-8"))["mappings"]
            matches = [r for r in rows if r.get("active") is True
                       and r.get("issuer") == s.auth_mode and r.get("actor_id") == str(actor.actor_id)
                       and r.get("organization_id") == str(actor.organization_id)
                       and r.get("contour") == "training" and r.get("instance_id") == s.interaction_legacy_instance]
            # Even duplicates with identical login are ambiguous, never pick the first.
            if len(matches) != 1:
                return None
            row = matches[0]
            if not isinstance(row.get("revision"), int) or row["revision"] < 1:
                return None
            if not isinstance(row.get("legacy_login"), str) or not row["legacy_login"]:
                return None
            uuid.UUID(row["legacy_user_id"])
            if row.get("legacy_role") not in {"admin", "hr", "department"}:
                return None
            if not any(g.role == row["legacy_role"] and g.scope_type == row.get("scope_type")
                       and str(g.scope_id) == row.get("scope_id") for g in actor.grants):
                return None
            if row["legacy_role"] in {"hr", "admin"} and (
                row["scope_type"] != "organization" or row["scope_id"] != str(actor.organization_id)
            ):
                return None
            if row["legacy_role"] == "department" and row["scope_type"] != "department":
                return None
            return row
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    def portal_read(self, actor, **filters):
        if not self.portal_slots.acquire(blocking=False):
            raise SourceFailure("SOURCE_BUSY")
        try:
            with Session(self.engine) as session, session.begin():
                if self.engine.dialect.name == "postgresql":
                    milliseconds = int(self.settings.interaction_read_seconds * 1000)
                    session.execute(text("SELECT set_config('statement_timeout', :value, true)"),
                                    {"value": str(milliseconds)})
                return read_portal_source(session, actor, self.settings, **filters)
        finally:
            self.portal_slots.release()

    async def remote(self, mapping, method, path, *, params=None, body=b""):
        s = self.settings
        timeout = httpx.Timeout(s.interaction_read_seconds, connect=s.interaction_connect_seconds)
        headers = {"X-User-Login": mapping["legacy_login"], "X-Interaction-Gateway-Key": s.interaction_gateway_key,
                   "X-Interaction-User-Id": mapping["legacy_user_id"],
                   "Content-Type": "application/json", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=timeout, trust_env=False,
                                        follow_redirects=False) as client:
                async with client.stream(method, s.interaction_legacy_url.rstrip("/") + "/api/v1/" + path,
                                         headers=headers, params=params, content=body) as response:
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > s.interaction_max_bytes:
                            raise SourceFailure("SOURCE_RESPONSE_TOO_LARGE")
                    try:
                        result = json.loads(data)
                    except (ValueError, UnicodeError) as exc:
                        raise SourceFailure("SOURCE_INVALID_RESPONSE") from exc
                    return result, response.status_code
        except httpx.HTTPError as exc:
            raise SourceFailure() from exc

    def verify_binding(self, body, mapping):
        s = self.settings
        if not isinstance(body, dict) or body.get("gateway_enforced") is not True:
            raise SourceFailure("GATEWAY_NOT_ENFORCED", "not_linked")
        actor = body.get("actor", {})
        if not isinstance(actor, dict):
            raise SourceFailure("SOURCE_INVALID_RESPONSE")
        if (body.get("organization_id") != s.interaction_organization_id
            or body.get("instance_id") != s.interaction_legacy_instance
            or body.get("contour") != "training" or actor.get("login") != mapping["legacy_login"]
            or actor.get("user_id") != mapping["legacy_user_id"]
            or actor.get("role") != mapping["legacy_role"]):
            raise SourceFailure("IDENTITY_BINDING_REJECTED", "not_linked")

    async def legacy_read(self, actor, **filters):
        mapping = self.mapping(actor)
        if mapping is None:
            raise SourceFailure("IDENTITY_NOT_LINKED", "not_linked")
        context = {"actor_id": str(actor.actor_id), "mapping": mapping,
                   "filters": {k: v for k, v in filters.items() if k != "cursor"}}
        context = json.loads(json.dumps(context))
        raw_cursor = filters.get("cursor")
        if raw_cursor:
            try:
                encoded, signature = raw_cursor.split(".")
                expected = hmac.new(self.settings.interaction_cursor_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    raise ValueError("signature")
                cursor_data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                if cursor_data["context"] != context:
                    raise ValueError("scope")
                filters["cursor"] = cursor_data["cursor"]
            except (ValueError, KeyError, TypeError) as exc:
                raise Problem(422, "INVALID_CURSOR", "Reload the source page", "legacy_cursor") from exc
        body, status = await self.remote(mapping, "GET", "interaction-source",
                                         params={k: str(v) for k, v in filters.items() if v is not None})
        if status in {401, 403}:
            raise SourceFailure("IDENTITY_BINDING_REJECTED", "not_linked")
        if status in {400, 422}:
            raise Problem(422, "INVALID_CURSOR", "Reload the source page", "legacy_cursor")
        if status != 200:
            raise SourceFailure()
        self.verify_binding(body, mapping)
        source = body["source"]
        if source.get("next_cursor"):
            data = {"context": context, "cursor": source["next_cursor"]}
            encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
            source["next_cursor"] = encoded + "." + hmac.new(
                self.settings.interaction_cursor_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        return {**source, "items": body["items"]}

    async def read(self, actor, *, relation=None, subject_source=None, subject_kind=None,
                   subject_id=None, portal_cursor=None, legacy_cursor=None, page_size=25):
        if not self.settings.interaction_enabled:
            raise Problem(404, "NOT_FOUND", "Interaction window is not enabled")
        if relation is not None and relation not in RELATIONS:
            raise Problem(422, "VALIDATION_ERROR", "Unknown relation", "relation")
        focus = (subject_source, subject_kind, subject_id)
        if any(x is not None for x in focus):
            if not all(x is not None for x in focus) or (subject_source, subject_kind) not in {
                ("hiring.portal", "candidate_request"), ("legacy", "application")
            }:
                raise Problem(422, "VALIDATION_ERROR", "Use source, kind and id for one subject", "subject_ref")
        async def part(name, applicable, operation):
            if not applicable:
                return source_state(name, "not_applicable"), []
            try:
                value = await asyncio.wait_for(operation(), self.settings.interaction_overall_seconds)
                items = value.pop("items")
                if not isinstance(items, list) or len(items) > page_size:
                    raise SourceFailure("SOURCE_INVALID_RESPONSE")
                if len(json.dumps(items, ensure_ascii=False).encode("utf-8")) > self.settings.interaction_max_bytes:
                    raise SourceFailure("SOURCE_RESPONSE_TOO_LARGE")
                # Source owns authorization and template fields; only this defined source envelope is public.
                source = {key: value.get(key) for key in (
                    "source", "status", "observed_at", "source_as_of", "next_cursor", "coverage")}
                if source["source"] != name or source["status"] != "ok" or source["coverage"] not in {"page", "complete"}:
                    raise SourceFailure("SOURCE_INVALID_RESPONSE")
                return source, items
            except Problem as exc:
                if exc.status in {400, 422}:
                    raise
                return source_state(name, "unavailable", "SOURCE_UNAVAILABLE"), []
            except SourceFailure as exc:
                return source_state(name, exc.status, exc.code), []
            except Exception:
                # A source outage is a first-class result, never a cached success or a raw exception.
                return source_state(name, "unavailable", "SOURCE_UNAVAILABLE"), []
        portal_applicable = (actor.is_hr() or actor.is_candidate()) and subject_source in {None, "hiring.portal"}
        legacy_applicable = not actor.is_candidate() and subject_source in {None, "legacy"}
        common = {"relation": relation, "subject_id": subject_id, "page_size": page_size}
        results = await asyncio.gather(
            part("hiring.portal", portal_applicable,
                 lambda: asyncio.to_thread(self.portal_read, actor, cursor=portal_cursor, **common)),
            part("legacy", legacy_applicable,
                 lambda: self.legacy_read(actor, cursor=legacy_cursor, **common)))
        sources = [r[0] for r in results]
        items = [item for r in results for item in r[1]]
        applicable = [s for s in sources if s["status"] != "not_applicable"]
        successful = [s for s in applicable if s["status"] == "ok"]
        completeness = ("complete" if len(successful) == len(applicable)
                        else "partial" if successful else "unavailable")
        return {"schema_version": 1, "generated_at": now(), "completeness": completeness,
                "sources": sources, "items": items}, 503 if applicable and not successful else 200

    async def proxy(self, actor, method, path, body):
        if not self.settings.interaction_enabled or not any(re.fullmatch(p, path) for p in ROUTES.get(method, [])):
            raise Problem(404, "NOT_FOUND", "Unknown interaction action")
        mapping = self.mapping(actor)
        if mapping is None:
            raise Problem(403, "FORBIDDEN_SCOPE", "Legacy identity is not linked")
        if len(body) > self.settings.interaction_max_bytes:
            raise Problem(413, "BODY_TOO_LARGE", "Action body exceeds limit")
        async def dispatch():
            parts = path.split("/")
            kind = {"applications": "application", "handoffs": "handoff", "candidate-texts": "candidate_text"}.get(parts[0])
            target = {"target_kind": kind, "target_id": parts[1]} if kind else None
            session, status = await self.remote(mapping, "GET", "interaction-session", params=target)
            if status != 200:
                raise SourceFailure("IDENTITY_BINDING_REJECTED", "not_linked" if status in {401, 403} else "unavailable")
            self.verify_binding(session, mapping)
            # No automatic retry: a failed POST may already have committed at the source.
            return await self.remote(mapping, method, path, body=body,
                                     params={"contour": "training"})
        try:
            return await asyncio.wait_for(dispatch(), self.settings.interaction_overall_seconds)
        except SourceFailure as exc:
            raise Problem(403 if exc.status == "not_linked" else 503, exc.code,
                          "Source unavailable; reread before retrying the same request_id") from exc
        except TimeoutError as exc:
            raise Problem(503, "SOURCE_TIMEOUT", "Result unknown; reread before retrying the same request_id") from exc
