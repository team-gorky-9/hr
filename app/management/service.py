"""4A: текущая кадровая работа и факты телефонных встреч за период.

Пример. HR запрашивает overview за 20.11–21.11 (to исключительно) в учебном контуре. В базе три
встречи: разговор continue 20.11 в 23:59 МСК, попытка no_answer 20.11 и открытая встреча без итога.
Ответ: held_count=1, no_answer_count=1, open_count=1, by_interviewer — у hr_demo один continue.
Разговор 21.11 в 00:00 МСК в этот период не входит. Воронка — существующая /analytics/funnel с её
правилами; период закрытий в ней задаётся включительно, поэтому to-1 день.
Вопросы гайда и записанные ответы встречу проведённой не делают: учитывается только held_at."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas import Contour
from app.api.workflow import REPORT_TZ, funnel
from app.db.enums import InterviewKind, InterviewResult
from app.db.models import Application, Candidate, Interview, User
from app.management.schemas import (
    InterviewerRow,
    InterviewsBlock,
    OverviewOut,
    OverviewPeriod,
    OverviewSource,
    SourceStatus,
)

UNITS = {
    "held_count": "interview — состоявшийся телефонный разговор (held_at в периоде); звонки одного отклика считаются отдельно",
    "held_applications_count": "application — разные отклики, по которым в периоде был разговор",
    "no_answer_count": "interview — неуспешная попытка связи (result=no_answer, attempt_at в периоде)",
    "open_count": "interview — открытая встреча без итога (pending) на момент среза, вне периода",
    "undated_count": "interview — встреча с итогом, но без даты разговора/попытки; в период не попадает",
}
NOT_CONNECTED = "Подключение к журналу не настроено в legacy API: сведения не запрашивались и не заявляются"


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=REPORT_TZ)


def interview_schema_ready(session: Session) -> bool:
    """Поля итога встречи появились в миграции 0010 (wave-2). Без них источник интервью недоступен."""
    columns = {c["name"] for c in inspect(session.connection()).get_columns("interviews")}
    return {"held_at", "attempt_at", "result", "outcome_recorded_at"} <= columns


def interviews_block(session: Session, contour: Contour, start: datetime, end: datetime) -> InterviewsBlock:
    if not interview_schema_ready(session):
        return InterviewsBlock(status="unavailable", units=UNITS,
                               coverage_note="Журнал встреч без полей итога (нужна миграция 0010): счётчики не выдаются")
    rows = session.execute(
        select(Interview.application_id, Interview.interviewer_user_id, Interview.result,
               Interview.held_at, Interview.attempt_at)
        .join(Application, Application.id == Interview.application_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .where(Interview.kind == InterviewKind.PHONE, Candidate.is_synthetic == (contour == Contour.TRAINING))
    ).all()

    held = no_answer = open_count = undated = 0
    held_applications = set()
    people: dict = defaultdict(lambda: {"held": 0, "no_answer": 0, "continue": 0, "stop": 0, "pending": 0})
    for application_id, interviewer, result, held_at, attempt_at in rows:
        result = InterviewResult(result)
        if result == InterviewResult.PENDING:
            open_count += 1
            if interviewer is not None:
                people[interviewer]["pending"] += 1
            continue
        if result == InterviewResult.NO_ANSWER:
            # Попытка связи — не разговор, даже если поле held_at по ошибке заполнено.
            if attempt_at is None:
                undated += 1
            elif start <= attempt_at < end:
                no_answer += 1
                people[interviewer]["no_answer"] += 1
            continue
        if held_at is None:  # continue/stop без даты разговора — не превращаем в проведённый
            undated += 1
        elif start <= held_at < end:
            held += 1
            held_applications.add(application_id)
            people[interviewer]["held"] += 1
            people[interviewer][str(result)] += 1

    logins = dict(session.execute(select(User.id, User.login).where(
        User.id.in_([p for p in people if p is not None]))).all()) if people else {}
    by_interviewer = [
        InterviewerRow(interviewer_user_id=uid, login=logins.get(uid), held_count=c["held"],
                       no_answer_count=c["no_answer"],
                       outcomes={"continue": c["continue"], "stop": c["stop"], "pending": c["pending"]})
        for uid, c in sorted(people.items(), key=lambda item: (item[0] is None, logins.get(item[0]) or "", str(item[0])))
    ]
    note = (f"Зарегистрированные телефонные встречи legacy-hr в контуре {contour}: {len(rows)} в журнале. "
            "Это не полный кадровый охват организации. Проведённой считается встреча с held_at; "
            "наличие гайда или ответов встречу не завершает.")
    if not rows:
        note = f"0 зарегистрировано в этом журнале (legacy-hr, контур {contour}). Полный кадровый охват не заявляется."
    return InterviewsBlock(status="available", held_count=held, held_applications_count=len(held_applications),
                           no_answer_count=no_answer, open_count=open_count, undated_count=undated,
                           by_interviewer=by_interviewer, units=UNITS, coverage_note=note)


def overview(session: Session, contour: Contour, period_from: date, period_to: date) -> OverviewOut:
    if period_from >= period_to:
        raise ApiError(422, "INVALID_PERIOD", "Начало периода должно быть раньше конца (to — исключительно)",
                       {"from": period_from.isoformat(), "to": period_to.isoformat()})
    start, end = day_start(period_from), day_start(period_to)
    # Существующая воронка: закрытия за период включительно по дням, поэтому последний день — to-1.
    funnel_out = funnel(session, contour, None, None, period_from, period_to - timedelta(days=1))
    interviews = interviews_block(session, contour, start, end)
    generated_at = funnel_out.as_of
    sources = [
        SourceStatus(key="legacy-hr.applications", status="available", observed_at=generated_at,
                     note="Отклики площадки и переходы этапов; правила и единицы — /analytics/funnel"),
        SourceStatus(key="legacy-hr.interviews", status=interviews.status,
                     observed_at=generated_at if interviews.status == "available" else None,
                     note=interviews.coverage_note),
        SourceStatus(key="workforce", status="unavailable", observed_at=None, note=NOT_CONNECTED),
        SourceStatus(key="hiring", status="unavailable", observed_at=None, note=NOT_CONNECTED),
        SourceStatus(key="practice", status="unavailable", observed_at=None, note=NOT_CONNECTED),
    ]
    return OverviewOut(generated_at=generated_at, period=OverviewPeriod(from_=period_from, to=period_to),
                       source=OverviewSource(contour=contour), funnel=funnel_out, interviews=interviews,
                       sources=sources)
