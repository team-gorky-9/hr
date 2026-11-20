"""Утверждение профиля отдельной командой (scripts/approve_profile.py) — шаг qa-01."""
import pytest

from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load
from app.db import repository as repo
from app.db.enums import RequirementStatus, UserRole
from app.db.models import User
from scripts.approve_profile import approver, find_draft

FIXTURE = load(FIXTURES_DIR / "py-9001.json")


def test_latest_training_draft_is_approved_and_previous_archived(session):
    first = create_fixture_profile(session, FIXTURE)
    second = create_fixture_profile(session, FIXTURE)
    user, created = approver(session, "hr-demo", "Кадровик (демо)")
    assert created and user.role == UserRole.HR

    assert find_draft(session, profile_id=None, position_code="python-dev", synthetic=True).id == second.id
    repo.approve_requirement_profile(session, first.id, approved_by_user_id=user.id, approval_basis="qa-01")
    draft = find_draft(session, profile_id=None, position_code="python-dev", synthetic=True)
    repo.approve_requirement_profile(session, draft.id, approved_by_user_id=user.id, approval_basis="qa-01")

    session.refresh(first)
    position_id = second.position_id
    assert first.status == RequirementStatus.ARCHIVED
    assert repo.get_approved_profile(session, position_id, synthetic=True).id == second.id
    assert repo.get_approved_profile(session, position_id) is None  # рабочий контур не тронут


def test_existing_user_is_reused_and_not_changed(session):
    session.add(User(login="dept-1", full_name="Руководитель", role=UserRole.DEPARTMENT, is_active=True))
    session.flush()
    user, created = approver(session, "dept-1", "другое имя")
    assert not created and user.role == UserRole.DEPARTMENT and user.full_name == "Руководитель"
    profile = create_fixture_profile(session, FIXTURE)
    with pytest.raises(repo.RepositoryError, match="кадровик"):
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=user.id, approval_basis="qa-01")


def test_no_draft_in_contour_is_reported(session):
    create_fixture_profile(session, FIXTURE)  # учебный
    with pytest.raises(SystemExit, match="нет черновика рабочего профиля"):
        find_draft(session, profile_id=None, position_code="python-dev", synthetic=False)
