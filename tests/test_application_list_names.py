from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response

from app.api import candidates, routes
from app.api.errors import ApiError
from app.db.enums import Channel, UserRole


def test_list_names_are_staff_only_and_audited(monkeypatch):
    ident = uuid4()
    accessed = []
    commits = []
    session = SimpleNamespace(commit=lambda: commits.append(True))
    monkeypatch.setattr(routes.services, 'list_applications', lambda *args, **kwargs:
        SimpleNamespace(items=[SimpleNamespace(candidate_id=ident, full_name=None)]))
    def read_pii(db, candidate_id, **kwargs):
        accessed.append((candidate_id, kwargs))
        return SimpleNamespace(full_name='Алексей Учебный')
    monkeypatch.setattr(routes.repo, 'get_candidate_pii', read_pii)
    public = routes.list_applications(uuid4(), session, Response(), user=None)
    assert public.items[0].full_name is None
    assert not accessed and not commits
    for role in (UserRole.HR, UserRole.ADMIN):
        actor = SimpleNamespace(role=role, id=uuid4())
        response = Response()
        result = routes.list_applications(uuid4(), session, response, user=actor)
        assert result.items[0].full_name == 'Алексей Учебный'
        assert accessed[-1][1]['user_id'] == actor.id
        assert accessed[-1][1]['purpose'] == 'список откликов: имя кандидата'
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.headers['vary'] == 'X-User-Login'
    assert len(commits) == 2


def test_department_cannot_read_name_list(monkeypatch):
    monkeypatch.setattr(routes.services, 'list_applications', lambda *args, **kwargs:
        pytest.fail('Department reached the list query'))
    with pytest.raises(ApiError):
        routes.list_applications(uuid4(), None, Response(), user=SimpleNamespace(role=UserRole.DEPARTMENT))


def test_candidate_registry_names_are_hr_only_and_audited(monkeypatch):
    ident = uuid4()
    accessed = []
    commits = []
    candidate = SimpleNamespace(id=ident, code='hr-9101', headline='Специалист', is_synthetic=True)
    session = SimpleNamespace(
        execute=lambda query: [(candidate, Channel.HH_RU, None, False, None, None, None)],
        commit=lambda: commits.append(True),
    )

    def read_pii(db, candidate_id, **kwargs):
        accessed.append((candidate_id, kwargs))
        return SimpleNamespace(full_name='Ирина Андреевна Сорокина')

    monkeypatch.setattr(candidates.repo, 'get_candidate_pii', read_pii)
    actor = SimpleNamespace(role=UserRole.HR, id=uuid4())
    response = Response()
    result = candidates.list_candidates(session, actor, response)
    assert result.items[0].full_name == 'Ирина Андреевна Сорокина'
    assert accessed[-1][1]['user_id'] == actor.id
    assert accessed[-1][1]['purpose'] == 'единая база: имя кандидата'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['vary'] == 'X-User-Login'
    assert len(commits) == 1
