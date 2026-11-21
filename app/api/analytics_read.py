"""Period-scoped recruiting aggregates for the operational dashboard."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import StaffUser
from app.api.errors import ApiError, not_found
from app.api.schemas import Contour
from app.api.workflow import REPORT_TZ, period_bounds
from app.db.enums import ApplicationSource, HandoffStatus
from app.db.models import Application, Candidate, HandoffAttempt, Interview, RejectionReason, SelectionStage, StageEvent, Vacancy
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


class TimeseriesWeek(BaseModel):
    start: date
    end: date
    screened: int
    interviews: int


class NamedCount(BaseModel):
    code: str
    title: str
    count: int


class ChannelCount(BaseModel):
    channel: str
    count: int


class VacancyMetrics(BaseModel):
    id: UUID
    title: str
    received: int
    interviews: int
    forwarded: int
    days_open: int | None
    waiting: int
    due_soon: int
    overdue: int


class DashboardTotals(BaseModel):
    received: int
    screened: int
    interviews: int
    hired: int
    forwarded: int


class DashboardOut(BaseModel):
    as_of: datetime
    period_from: date
    period_to: date
    totals: DashboardTotals
    weeks: list[TimeseriesWeek]
    stages: list[NamedCount]
    sources: list[ChannelCount]
    rejections: list[NamedCount]
    vacancies: list[VacancyMetrics]


def week_periods(start: date, end: date) -> list[tuple[date, date]]:
    weeks = []
    while start <= end:
        last_day = start + timedelta(days=min((end - start).days, 6 - start.weekday()))
        weeks.append((start, last_day))
        start = last_day + timedelta(days=1)
    return weeks


def utc_period(start: date, end: date) -> tuple[datetime, datetime]:
    first, after_last = period_bounds(start, end)
    assert first is not None and after_last is not None
    return first.astimezone(timezone.utc), after_last.astimezone(timezone.utc)


def dashboard(
    session: Session,
    *,
    contour: Contour,
    period_from: date,
    period_to: date,
    vacancy_id: UUID | None,
    as_of: datetime,
) -> DashboardOut:
    if period_from == date.min or period_to == date.max or not 0 <= (period_to - period_from).days < 366:
        raise ApiError(422, "INVALID_PERIOD", "Укажите период от 1 до 366 календарных дней")

    selected_vacancies = select(Vacancy.id, Vacancy.title, Vacancy.channel, Vacancy.opened_at, Vacancy.closed_at)
    if vacancy_id is not None:
        selected_vacancies = selected_vacancies.where(Vacancy.id == vacancy_id)
    vacancies = list(session.execute(selected_vacancies.order_by(Vacancy.title, Vacancy.id)))
    if vacancy_id is not None and not vacancies:
        raise not_found("VACANCY_NOT_FOUND", "Вакансия не найдена", vacancy_id=vacancy_id)

    applications = (
        select(Application.id, Application.vacancy_id, Application.applied_at)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .where(
            Application.vacancy_id.is_not(None),
            Application.source == ApplicationSource.RESPONSE,
            Candidate.is_synthetic == (contour == Contour.TRAINING),
        )
    )
    if vacancy_id is not None:
        applications = applications.where(Application.vacancy_id == vacancy_id)
    scope = applications.cte("dashboard_applications")

    received = dict(session.execute(
        select(scope.c.vacancy_id, func.count())
        .where(scope.c.applied_at.between(period_from, period_to))
        .group_by(scope.c.vacancy_id)
    ).all())

    start, end = utc_period(period_from, period_to)
    event_range = (StageEvent.created_at >= start, StageEvent.created_at < end)
    interview_range = (Interview.held_at >= start, Interview.held_at < end)
    stage_rows = session.execute(
        select(SelectionStage.code, SelectionStage.title, func.count(func.distinct(StageEvent.application_id)))
        .join(StageEvent, StageEvent.to_stage_code == SelectionStage.code)
        .join(scope, scope.c.id == StageEvent.application_id)
        .where(*event_range)
        .group_by(SelectionStage.code, SelectionStage.title, SelectionStage.sort_order)
        .order_by(SelectionStage.sort_order)
    ).all()
    stages = [NamedCount(code=code, title=title, count=count) for code, title, count in stage_rows]
    stage_counts = {stage.code: stage.count for stage in stages}

    interviews = dict(session.execute(
        select(scope.c.vacancy_id, func.count(Interview.id))
        .select_from(Interview)
        .join(scope, scope.c.id == Interview.application_id)
        .where(*interview_range)
        .group_by(scope.c.vacancy_id)
    ).all())

    weeks = week_periods(period_from, period_to)
    week_bounds = [utc_period(first, last) for first, last in weeks]
    screened_by_week = session.execute(
        select(*(func.count(func.distinct(StageEvent.application_id)).filter(
            StageEvent.created_at >= first, StageEvent.created_at < last,
        ) for first, last in week_bounds))
        .select_from(StageEvent)
        .join(scope, scope.c.id == StageEvent.application_id)
        .where(*event_range, StageEvent.to_stage_code == "screening")
    ).one()
    interviews_by_week = session.execute(
        select(*(func.count(Interview.id).filter(Interview.held_at >= first, Interview.held_at < last)
                 for first, last in week_bounds))
        .select_from(Interview)
        .join(scope, scope.c.id == Interview.application_id)
        .where(*interview_range)
    ).one()

    rejection_rows = session.execute(
        select(StageEvent.rejection_reason_code, RejectionReason.title, func.count())
        .select_from(StageEvent)
        .join(scope, scope.c.id == StageEvent.application_id)
        .outerjoin(RejectionReason, RejectionReason.code == StageEvent.rejection_reason_code)
        .where(*event_range, StageEvent.to_stage_code.in_(("rejected", "withdrawn")))
        .group_by(StageEvent.rejection_reason_code, RejectionReason.title)
        .order_by(func.count().desc(), StageEvent.rejection_reason_code)
    ).all()

    today = as_of.astimezone(REPORT_TZ).date()
    waiting = (
        HandoffAttempt.status == HandoffStatus.AWAITING_RESPONSE,
        HandoffAttempt.access_revoked_at.is_(None),
    )
    handoff_rows = session.execute(
        select(
            scope.c.vacancy_id,
            func.count(func.distinct(HandoffAttempt.application_id)),
            func.count().filter(*waiting),
            func.count().filter(*waiting, HandoffAttempt.reminder_date <= today, HandoffAttempt.due_date >= today),
            func.count().filter(*waiting, HandoffAttempt.due_date < today),
        )
        .select_from(HandoffAttempt)
        .join(scope, scope.c.id == HandoffAttempt.application_id)
        .where(HandoffAttempt.handed_off_at >= start, HandoffAttempt.handed_off_at < end)
        .group_by(scope.c.vacancy_id)
    ).all()
    handoffs = {ident: (sent, pending, due_soon, overdue) for ident, sent, pending, due_soon, overdue in handoff_rows}

    vacancy_rows = []
    source_counts: Counter[str] = Counter()
    for ident, title, channel, opened_at, closed_at in vacancies:
        count = received.get(ident, 0)
        if count:
            source_counts[str(channel)] += count
        days_open = None
        active_until = min(period_to, today, closed_at or date.max)
        if opened_at is not None and opened_at <= active_until:
            days_open = (active_until - opened_at).days
        sent, pending, due_soon, overdue = handoffs.get(ident, (0, 0, 0, 0))
        vacancy_rows.append(VacancyMetrics(
            id=ident, title=title, received=count, interviews=interviews.get(ident, 0), forwarded=sent,
            days_open=days_open, waiting=pending, due_soon=due_soon, overdue=overdue,
        ))

    return DashboardOut(
        as_of=as_of, period_from=period_from, period_to=period_to,
        totals=DashboardTotals(
            received=sum(received.values()), screened=stage_counts.get("screening", 0),
            interviews=sum(interviews.values()), hired=stage_counts.get("hired", 0),
            forwarded=sum(row.forwarded for row in vacancy_rows),
        ),
        weeks=[TimeseriesWeek(start=first, end=last, screened=screened, interviews=held)
               for (first, last), screened, held in zip(weeks, screened_by_week, interviews_by_week, strict=True)],
        stages=stages,
        sources=[ChannelCount(channel=channel, count=count) for channel, count in source_counts.most_common()],
        rejections=[NamedCount(code=code or "unknown", title=title or "Причина не указана", count=count)
                    for code, title, count in rejection_rows],
        vacancies=vacancy_rows,
    )


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    session: Annotated[Session, Depends(get_session)],
    user: StaffUser,
    period_from: date,
    period_to: date,
    contour: Contour = Contour.WORKING,
    vacancy_id: UUID | None = None,
) -> DashboardOut:
    return dashboard(
        session, contour=contour, period_from=period_from, period_to=period_to,
        vacancy_id=vacancy_id, as_of=datetime.now(timezone.utc),
    )
