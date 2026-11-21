from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.analytics_read import dashboard, router
from app.api.errors import ApiError
from app.api.schemas import Contour
from app.db.enums import UserRole
from app.db.models import User


def test_dashboard_filters_each_business_event_by_its_own_date():
    # Minimal schema exercises the actual aggregate selects without requiring a
    # local PostgreSQL server. All stored timestamps are UTC as on the stand.
    engine = create_engine("sqlite://")
    first, second = uuid4(), uuid4()
    old, new, other, working = [uuid4() for _ in range(4)]
    with Session(engine) as session:
        sql = session.connection().exec_driver_sql
        for schema in (
            "vacancies (id TEXT, title TEXT, channel TEXT, opened_at DATE, closed_at DATE)",
            "candidates (id TEXT, is_synthetic BOOL)",
            "applications (id TEXT, candidate_id TEXT, vacancy_id TEXT, source TEXT, applied_at DATE)",
            "selection_stages (code TEXT, title TEXT, sort_order INTEGER)",
            "stage_events (application_id TEXT, to_stage_code TEXT, rejection_reason_code TEXT, created_at DATETIME)",
            "interviews (id TEXT, application_id TEXT, held_at DATETIME)",
            "rejection_reasons (code TEXT, title TEXT)",
            "handoff_attempts (application_id TEXT, status TEXT, access_revoked_at DATETIME, handed_off_at DATETIME, due_date DATE, reminder_date DATE)",
        ):
            sql("CREATE TABLE " + schema)
        sql("INSERT INTO vacancies VALUES (?, 'First', 'hh_ru', '2026-11-01', null), (?, 'Second', 'email', '2026-11-01', null)",
            (first.hex, second.hex))
        for application, vacancy, synthetic, applied in (
            (old, first, True, "2026-11-15"), (new, first, True, "2026-11-21"),
            (other, second, True, "2026-11-23"), (working, second, False, "2026-11-23"),
        ):
            candidate = uuid4().hex
            sql("INSERT INTO candidates VALUES (?, ?)", (candidate, synthetic))
            sql("INSERT INTO applications VALUES (?, ?, ?, 'response', ?)", (application.hex, candidate, vacancy.hex, applied))
        sql("INSERT INTO selection_stages VALUES ('screening','Отбор',1), ('rejected','Отказ',2)")
        sql("INSERT INTO rejection_reasons VALUES ('experience', 'Опыт')")
        # 21:00 UTC is midnight in Moscow. The first event falls before the period.
        sql("INSERT INTO stage_events VALUES (?, 'screening', null, '2026-11-20 20:59:00.000000'), "
            "(?, 'screening', null, '2026-11-20 21:00:00.000000'), "
            "(?, 'screening', null, '2026-11-21 11:00:00.000000'), "
            "(?, 'screening', null, '2026-11-23 11:00:00.000000'), "
            "(?, 'rejected', 'experience', '2026-11-23 12:00:00.000000')",
            (new.hex, old.hex, old.hex, other.hex, other.hex))
        sql("INSERT INTO interviews VALUES ('held', ?, '2026-11-23 09:00:00.000000'), ('not-held', ?, null)",
            (old.hex, new.hex))
        sql("INSERT INTO handoff_attempts VALUES (?, 'awaiting_response', null, '2026-11-21 10:00:00.000000', '2026-11-22', '2026-11-21')", (old.hex,))
        scope = dict(contour=Contour.TRAINING, period_from=date(2026, 11, 21), period_to=date(2026, 11, 24),
                     as_of=datetime(2026, 11, 24, 12, tzinfo=timezone.utc))

        data = dashboard(session, vacancy_id=None, **scope)
        assert data.totals.model_dump() == dict(received=2, screened=2, interviews=1, hired=0, forwarded=1)
        assert [(row.start.day, row.end.day, row.screened, row.interviews) for row in data.weeks] == [
            (21, 22, 1, 0), (23, 24, 1, 1),
        ]
        assert {row.channel: row.count for row in data.sources} == {"hh_ru": 1, "email": 1}
        assert [(row.code, row.count) for row in data.rejections] == [("experience", 1)]
        assert data.vacancies[0].waiting == data.vacancies[0].overdue == 1

        selected = dashboard(session, vacancy_id=first, **scope)
        assert [(row.id, row.received, row.interviews) for row in selected.vacancies] == [(first, 1, 1)]
        assert selected.rejections == []
        assert [row.channel for row in selected.sources] == ["hh_ru"]


def test_dashboard_route_requires_staff_role():
    route = next(route for route in router.routes if route.path.endswith("/dashboard"))
    require_staff = next(dependency.call for dependency in route.dependant.dependencies if dependency.name == "user")
    with pytest.raises(ApiError) as failure:
        require_staff(User(role=UserRole.DEPARTMENT))
    assert failure.value.status_code == 403
