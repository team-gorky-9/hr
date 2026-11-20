"""Утверждение профиля отдельной командой (scripts/approve_profile.py) — шаг qa-01."""
from contextlib import nullcontext
import json

import pytest
from sqlalchemy import select

from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load
from app.db import repository as repo
from app.db.enums import RequirementStatus, UserRole
from app.db.models import User
from scripts.approve_profile import approver, find_draft
from tests import factories as f

FIXTURE = load(FIXTURES_DIR / "py-9001.json")


def test_latest_training_draft_is_approved_and_previous_archived(session):
    first = create_fixture_profile(session, FIXTURE)
    second = create_fixture_profile(session, FIXTURE)
    session.add(User(login="hr-demo", full_name="Кадровик (демо)", role=UserRole.HR, is_active=True))
    session.flush()
    user = approver(session, "hr-demo")
    assert user.role == UserRole.HR

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
    user = approver(session, "dept-1")
    assert user.role == UserRole.DEPARTMENT and user.full_name == "Руководитель"
    profile = create_fixture_profile(session, FIXTURE)
    with pytest.raises(repo.RepositoryError, match="кадровик"):
        repo.approve_requirement_profile(session, profile.id, approved_by_user_id=user.id, approval_basis="qa-01")


def test_no_draft_in_contour_is_reported(session):
    create_fixture_profile(session, FIXTURE)  # учебный
    with pytest.raises(SystemExit, match="нет черновика рабочего профиля"):
        find_draft(session, profile_id=None, position_code="python-dev", synthetic=False)


@pytest.mark.parametrize('synthetic', [False, True])
@pytest.mark.parametrize('by_id', [False, True])
def test_cli_missing_approver_leaves_profile_and_users_unchanged(session, monkeypatch, capsys, synthetic, by_id):
    from app.db import session as db_session
    from scripts.approve_profile import main

    profile = f.make_profile(session, position_code='python-dev', is_synthetic=synthetic)
    session.commit()  # данные существуют до запуска команды с её отдельным rollback
    monkeypatch.setattr(db_session, 'SessionLocal', lambda: nullcontext(session))
    target = ['--profile-id', str(profile.id)] if by_id else ['--position-code', 'python-dev']
    if synthetic:
        target += ['--synthetic']
    assert main(target + ['--approver', 'unknown-hr', '--basis', 'test', '--commit']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'refused'
    assert session.scalar(select(User).where(User.login == 'unknown-hr')) is None
    session.refresh(profile)
    assert profile.status == RequirementStatus.DRAFT
    assert repo.get_approved_profile(session, profile.position_id, synthetic=synthetic) is None


@pytest.mark.parametrize('role,active,commit,expected', [
    (UserRole.HR, True, True, 'approved'),
    (UserRole.ADMIN, True, True, 'approved'),
    (UserRole.HR, True, False, 'dry_run'),
    (UserRole.HR, False, True, 'refused'),
    (UserRole.DEPARTMENT, True, True, 'refused'),
])
def test_cli_existing_approver_permissions_and_rollback(session, monkeypatch, capsys, role, active, commit, expected):
    from app.db import session as db_session
    from scripts.approve_profile import main

    profile = f.make_profile(session)
    user = f.make_user(session, role=role, active=active)
    session.commit()
    monkeypatch.setattr(db_session, 'SessionLocal', lambda: nullcontext(session))
    args = ['--profile-id', str(profile.id), '--approver', user.login, '--basis', 'test']
    if commit:
        args.append('--commit')
    assert main(args) == (1 if expected == 'refused' else 0)
    output = json.loads(capsys.readouterr().out)
    assert output['status'] == expected
    session.refresh(profile)
    assert profile.status == (RequirementStatus.APPROVED if expected == 'approved' else RequirementStatus.DRAFT)
    session.refresh(user)
    assert (user.role, user.is_active) == (role, active)
