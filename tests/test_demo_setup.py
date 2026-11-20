"""Демо-стенд: учебные копии шести профилей утверждаются один раз, рабочие черновики не утверждаются."""
from contextlib import nullcontext

from sqlalchemy import select

from app.db import seed
from app.db.enums import RequirementStatus
from app.db.models import RequirementProfile


def test_training_profiles_are_idempotent_and_leave_working_drafts_unapproved(session, monkeypatch):
    from app.db import session as db_session
    from scripts import demo_setup

    seed.seed_all(session)
    monkeypatch.setattr(db_session, "SessionLocal", lambda: nullcontext(session))
    first = demo_setup.training_profiles()
    assert {row["status"] for row in first} == {"approved"} and len(first) == 6
    second = demo_setup.training_profiles()
    assert {row["status"] for row in second} == {"already"}
    profiles = session.scalars(select(RequirementProfile)).all()
    training = [p for p in profiles if p.is_synthetic]
    working = [p for p in profiles if not p.is_synthetic]
    assert len(training) == 6 and all(p.status == RequirementStatus.APPROVED for p in training)
    assert len(working) == 6 and all(p.status == RequirementStatus.DRAFT for p in working)
