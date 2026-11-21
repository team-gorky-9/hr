"""Small SQLite domain scenario; no PostgreSQL fixtures or external services."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from hiring.auth import Actor, Grant
from hiring.errors import Problem
from hiring.models import Base, CandidateRequest, CandidateRequestMessage, Document
from hiring.portal import Portal
from hiring import schemas as s


@compiles(JSONB, "sqlite")
def sqlite_json(element, compiler, **kw):
    return "JSON"


def test_q_ref_survives_upload_but_replaced_question_does_not():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    org = uuid4()
    c1_id, c2_id = uuid4(), uuid4()
    c1 = Actor(c1_id, "candidate", org, (Grant("candidate", "self", c1_id),))
    c2 = Actor(c2_id, "candidate2", org, (Grant("candidate", "self", c2_id),))
    hr = Actor(uuid4(), "hr", org, (Grant("hr", "organization", org),))
    settings = SimpleNamespace(interaction_cursor_secret="test-only")
    with Session(engine) as session:
        row = CandidateRequest(organization_id=org, author_actor_id=c1_id, status="submitted",
                               message="PRIVATE MESSAGE", contact={"email": "PRIVATE EMAIL"})
        session.add(row)
        session.flush()
        hp, cp = Portal(session, hr, settings), Portal(session, c1, settings)
        q1 = hp.request_information(row.id, s.InformationRequest(expected_revision=row.revision,
                                     public_message="Question one", requested_items=["Resume"]))
        q1_ref = q1["information_request_ref"]
        assert q1_ref["request_id"] == str(row.id)
        from hiring.interaction_portal import read_portal_source
        def read(actor, **kwargs):
            return read_portal_source(session, actor, settings, **kwargs)
        candidate_item = read(c1)["items"][0]
        assert candidate_item["expectation_ref"] == q1_ref
        assert candidate_item["relation"] == "needs_my_action"
        assert read(hr)["items"][0]["relation"] == "waiting_on_other"
        assert read(c2)["items"] == []
        assert "PRIVATE" not in json.dumps(candidate_item)
        message = session.scalar(select(CandidateRequestMessage))
        revision = row.revision
        first_read = cp.mark_read(row.id, message.id)
        assert cp.mark_read(row.id, message.id)["read_at"] == first_read["read_at"]
        assert row.revision == revision and row.status == "needs_information"
        # A document upload changes the request revision, but not the pending question.
        document = Document(id=uuid4(), organization_id=org, kind="candidate_addendum",
                            original_name="resume.txt", media_type="text/plain", size_bytes=10,
                            sha256="a" * 64, uploaded_by=c1_id, uploaded_by_role="candidate", storage_key="test")
        cp.attach(row.id, document)
        answered = cp.add_addendum(row.id, s.Addendum(expected_revision=row.revision,
                                information_request_ref=q1_ref, text="My answer", document_ids=[document.id]))
        assert answered["status"] == "submitted"
        assert read(hr)["items"][0]["reason_code"] == "addendum_requires_review"
        assert read(c1)["items"][0]["relation"] == "waiting_on_other"
        q2 = hp.request_information(row.id, s.InformationRequest(expected_revision=row.revision,
                                     public_message="Question two", requested_items=["Experience"]))
        assert q2["information_request_ref"] != q1_ref
        with pytest.raises(Problem) as stale:
            cp.add_addendum(row.id, s.Addendum(expected_revision=row.revision,
                           information_request_ref=q1_ref, text="Late answer"))
        assert stale.value.status == 409 and stale.value.field == "information_request_ref"
        with pytest.raises(Problem):
            cp.add_addendum(row.id, s.Addendum(expected_revision=row.revision, text="Missing reference"))
        with pytest.raises(Problem) as hidden:
            Portal(session, c2, settings).get(row.id)
        assert hidden.value.status == 404
        # Source pagination filters in SQL, keeps equal-time IDs stable, binds cursors to identity/filter.
        session.add(CandidateRequest(organization_id=org, author_actor_id=c1_id, status="submitted",
                                    message="PRIVATE SECOND", contact={}))
        session.flush()
        filtered = read(c1, relation="waiting_on_other", page_size=1)
        assert len(filtered["items"]) == 1 and filtered["next_cursor"] is None
        page = read(c1, page_size=1)
        next_page = read(c1, page_size=1, cursor=page["next_cursor"])
        assert page["items"][0]["key"] != next_page["items"][0]["key"]
        assert next_page["next_cursor"] is None
        for actor, extra in [(c2, {}), (c1, {"relation": "needs_my_action"})]:
            with pytest.raises(Problem):
                read(actor, cursor=page["next_cursor"], page_size=1, **extra)
        # A manually linked consideration is visible to HR only, including through history.
        row.consideration = {"application_ref": {"system": "legacy-hr-training", "id": str(uuid4())},
                             "identity_basis": "PRIVATE IDENTITY BASIS", "recorded_at": "2026-01-01T00:00:00+00:00",
                             "selected_vacancy": {"title": "Economist", "position_code": "ECON"}}
        hp.record(row, "consideration.recorded", row.consideration)
        assert read(hr, subject_id=row.id)["items"][0]["related_ref"]["id"] == row.consideration["application_ref"]["id"]
        assert read(c1, subject_id=row.id)["items"][0]["related_ref"] is None
        assert "PRIVATE IDENTITY BASIS" not in json.dumps(cp.history(row.id))
        assert "PRIVATE IDENTITY BASIS" in json.dumps(hp.history(row.id))
        # An old question stays compatible in its source API, but cannot acquire an invented Q-ref.
        row.information_request = {"public_message": "Old question", "requested_items": ["Resume"],
                                   "requested_at": "2026-01-01T00:00:00+00:00", "answered": False}
        old_item = read(c1, subject_id=row.id)["items"][0]
        assert old_item["reason_code"] == "basis_unknown"
        assert old_item["actions"][0]["availability"] == "unavailable"
        assert cp.add_addendum(row.id, s.Addendum(expected_revision=row.revision, text="Historical reply"))["status"] == "submitted"
