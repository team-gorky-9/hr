"""Расчёт рабочих дней по производственному календарю РФ (справочник production_calendar_days).

Обычные суббота и воскресенье — выходные, будни (пн–пт) — рабочие, если в таблице
`production_calendar_days` для конкретной даты нет явного переопределения
(is_working_day = false для праздников/переносов, true для рабочих суббот).
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session


def load_calendar_overrides(session: Session) -> dict[date, bool]:
    """Загрузить все исключения/праздники производственного календаря из БД."""
    from app.db.models.selection import ProductionCalendarDay

    return dict(
        session.execute(select(ProductionCalendarDay.day, ProductionCalendarDay.is_working_day)).all()
    )


def is_working_day(day: date, overrides: dict[date, bool]) -> bool:
    """Является ли дата рабочим днём с учётом производственного календаря."""
    override = overrides.get(day)
    if override is not None:
        return override
    return day.weekday() < 5


def add_business_days(start_date: date, business_days: int, overrides: dict[date, bool]) -> date:
    """Прибавить N рабочих дней после start_date (день передачи считается днём 0)."""
    if business_days <= 0:
        return start_date
    current = start_date
    remaining = business_days
    while remaining > 0:
        current += timedelta(days=1)
        if is_working_day(current, overrides):
            remaining -= 1
    return current


def subtract_business_days(end_date: date, business_days: int, overrides: dict[date, bool]) -> date:
    """Отступить N рабочих дней назад от end_date (для пересчёта дня напоминания)."""
    if business_days <= 0:
        return end_date
    current = end_date
    remaining = business_days
    while remaining > 0:
        current -= timedelta(days=1)
        if is_working_day(current, overrides):
            remaining -= 1
    return current


def business_days_diff(from_date: date, to_date: date, overrides: dict[date, bool]) -> int:
    """Сколько рабочих дней в интервале (from_date, to_date]; отрицательно при to_date < from_date."""
    if from_date == to_date:
        return 0
    if to_date > from_date:
        count = 0
        current = from_date
        while current < to_date:
            current += timedelta(days=1)
            if is_working_day(current, overrides):
                count += 1
        return count
    return -business_days_diff(to_date, from_date, overrides)
