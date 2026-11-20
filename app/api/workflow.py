"""Действия кадровика, резерв, кросс-оценки и воронка (контракт api.md v0.3, раздел 3; задача backend-02).

Правила данных живут в app/db/repository.py: переход этапа, история, резерв без дублей.
Здесь — то, что добавляет HTTP:
- кто действует (пользователь из заголовка приходит из app/api/auth.py);
- какой код ответа у нарушенного правила (422 — неверный ввод, 409 — конфликт состояния);
- транзакция: сервис записи сам делает commit после успешного вызова репозитория,
  при ошибке сессия закрывается без commit и всё откатывается;
- сборка ответов.

Передача руководителю и ответ департамента — задача workflow-01, гайд и ответы интервью —
interview-01. Персональные данные API не отдаёт: модуль не читает candidate_pii.
"""
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import services
from app.api.errors import ApiError, not_found
from app.api.schemas import (
    Contour,
    CrossAssessmentItemOut,
    CrossAssessmentListOut,
    CrossVacancyOut,
    FunnelClosureOut,
    FunnelOut,
    FunnelStageOut,
    RejectionReasonListOut,
    RejectionReasonOut,
    ReserveCreatedOut,
    ReserveEntryOut,
    ReserveIn,
    ReserveListOut,
    ReserveWithdrawIn,
    StageEventOut,
    StageHistoryOut,
    StageMoveIn,
    StageMoveOut,
    StageOut,
    StageRefListOut,
    StageRefOut,
    UserBriefOut,
)
from app.db import repository as repo
from app.db.enums import ApplicationSource, CheckResult, RequirementStatus, ReserveStatus
from app.db.models import (
    Application,
    Candidate,
    CandidateCard,
    Position,
    RejectionReason,
    RequirementProfile,
    ReserveEntry,
    SelectionStage,
    StageEvent,
    User,
    Vacancy,
)

# Границы периода отчёта считаются по времени Нижнего Новгорода (МСК): дата «20.11» —
# это сутки 20.11 00:00–24:00 по Москве, а не по UTC.
REPORT_TZ = ZoneInfo("Europe/Moscow")
CLOSING_STAGES = ("hired", *repo.EXIT_STAGES)


# --- Общие помощники -------------------------------------------------------------

def get_application_or_404(session: Session, application_id: uuid.UUID) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise not_found("APPLICATION_NOT_FOUND", "Отклик не найден", application_id=application_id)
    return application


def require_working_application(application: Application) -> None:
    """Действия кадровика — только над откликами площадки (БД v1.6, п. 4.5).

    Внешний отклик из «Истории общения» — факт из прошлого; ручные записи (manual)
    по постановке backend-02 тоже не основание для рабочего действия.
    """
    if application.source != ApplicationSource.RESPONSE:
        raise ApiError(
            409,
            "NOT_WORKING_APPLICATION",
            "Действие доступно только для откликов с площадки",
            {"source": str(application.source)},
        )


def stage_out(stage: SelectionStage) -> StageOut:
    return StageOut(code=stage.code, title=stage.title, is_final=stage.is_final)


def reason_out(reason: RejectionReason | None) -> RejectionReasonOut | None:
    if reason is None:
        return None
    return RejectionReasonOut(code=reason.code, title=reason.title, side=reason.side)


def user_out(user: User | None) -> UserBriefOut | None:
    return UserBriefOut(login=user.login, role=str(user.role)) if user else None


def _users(session: Session, ids) -> dict[uuid.UUID, User]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {u.id: u for u in session.scalars(select(User).where(User.id.in_(ids)))}


def _stages(session: Session) -> dict[str, SelectionStage]:
    return {s.code: s for s in session.scalars(select(SelectionStage))}


def _reasons(session: Session) -> dict[str, RejectionReason]:
    return {r.code: r for r in session.scalars(select(RejectionReason))}


def _sentence(text: str) -> str:
    """Первая буква заглавная, остальное как есть (str.capitalize() испортил бы «Отказ» в кавычках)."""
    return text[:1].upper() + text[1:]


def _clean(text: str | None) -> str | None:
    """Пустая строка из формы — то же, что «не указано»."""
    if text is None:
        return None
    text = text.strip()
    return text or None


def last_seq(session: Session, application_id: uuid.UUID) -> int | None:
    return session.scalar(select(func.max(StageEvent.seq)).where(StageEvent.application_id == application_id))


# --- Справочники -------------------------------------------------------------------

def list_stages(session: Session) -> StageRefListOut:
    rows = session.scalars(select(SelectionStage).order_by(SelectionStage.sort_order))
    return StageRefListOut(
        items=[StageRefOut(code=s.code, title=s.title, sort_order=s.sort_order, is_final=s.is_final) for s in rows]
    )


def list_rejection_reasons(session: Session) -> RejectionReasonListOut:
    rows = session.scalars(select(RejectionReason).order_by(RejectionReason.side, RejectionReason.code))
    return RejectionReasonListOut(items=[reason_out(r) for r in rows])


# --- Этапы и история -------------------------------------------------------------

def _event_out(
    event: StageEvent,
    stages: dict[str, SelectionStage],
    reasons: dict[str, RejectionReason],
    users: dict[uuid.UUID, User],
) -> StageEventOut:
    return StageEventOut(
        seq=event.seq,
        from_stage=stage_out(stages[event.from_stage_code]) if event.from_stage_code else None,
        to_stage=stage_out(stages[event.to_stage_code]),
        rejection_reason=reason_out(reasons.get(event.rejection_reason_code)) if event.rejection_reason_code else None,
        actor=user_out(users.get(event.actor_user_id)),
        comment=event.comment,
        created_at=event.created_at,
    )


def move_stage(session: Session, application_id: uuid.UUID, body: StageMoveIn, user: User) -> StageMoveOut:
    """Ручной перевод этапа кадровиком.

    Порядок проверок:
    1. Ввод (422): неизвестный этап или причина; причина не к отказу; для перехода в
       «Отказ»/«Кандидат отказался» причина обязательна.
    2. Строка отклика блокируется (SELECT … FOR UPDATE), и последний seq истории сравнивается
       с expected_seq формы. Не совпал — форма устарела (вторая вкладка уже перевела отклик):
       409 STALE_STAGE_FORM. Блокировка держится до commit, поэтому из двух одновременных
       запросов с одним expected_seq пройдёт только первый.
    3. move_application проверяет правило этапов; его отказ (финальный этап, тот же этап,
       перескок без подтверждения) — 409 STAGE_TRANSITION_CONFLICT.
    """
    application = get_application_or_404(session, application_id)
    require_working_application(application)
    target = session.get(SelectionStage, body.to_stage_code)
    if target is None:
        raise ApiError(422, "UNKNOWN_STAGE_CODE", "Неизвестный этап отбора", {"to_stage_code": body.to_stage_code})
    if body.rejection_reason_code is not None and session.get(RejectionReason, body.rejection_reason_code) is None:
        raise ApiError(422, "UNKNOWN_REJECTION_REASON", "Неизвестная причина отказа",
                       {"rejection_reason_code": body.rejection_reason_code})
    if body.rejection_reason_code is not None and target.code not in repo.EXIT_STAGES:
        raise ApiError(422, "REJECTION_REASON_NOT_ALLOWED",
                       "Причина указывается только при переводе в «Отказ» или «Кандидат отказался»",
                       {"to_stage_code": target.code})
    if target.code in repo.EXIT_STAGES and body.rejection_reason_code is None:
        raise ApiError(422, "REJECTION_REASON_REQUIRED",
                       "Для отказа или отказа кандидата укажите причину из справочника",
                       {"to_stage_code": target.code})

    session.refresh(application, with_for_update=True)
    current_seq = last_seq(session, application.id)
    if current_seq != body.expected_seq:
        raise ApiError(409, "STALE_STAGE_FORM", "Отклик уже изменён в другом окне: обновите карточку",
                       {"expected_seq": body.expected_seq, "last_seq": current_seq,
                        "current_stage_code": application.current_stage_code})

    current_code = application.current_stage_code
    try:
        event = repo.move_application(
            session,
            application.id,
            target.code,
            actor_user_id=user.id,
            comment=_clean(body.comment),
            rejection_reason_code=body.rejection_reason_code,
            confirm_skip=body.confirm_skip,
        )
    except repo.StageTransitionError as error:
        # Текст правила из репозитория: по-русски и без данных кандидата.
        raise ApiError(409, "STAGE_TRANSITION_CONFLICT", _sentence(str(error)),
                       {"current_stage_code": current_code, "to_stage_code": target.code}) from error
    session.commit()

    stages = _stages(session)
    return StageMoveOut(
        application_id=application.id,
        stage=stage_out(stages[application.current_stage_code]),
        event=_event_out(event, stages, _reasons(session), {user.id: user}),
    )


def get_history(session: Session, application_id: uuid.UUID) -> StageHistoryOut:
    application = get_application_or_404(session, application_id)
    events = repo.stage_history(session, application.id)
    stages, reasons = _stages(session), _reasons(session)
    users = _users(session, (e.actor_user_id for e in events))
    return StageHistoryOut(
        application_id=application.id,
        source=application.source,
        stage=stage_out(stages[application.current_stage_code]),
        last_seq=events[-1].seq if events else None,
        items=[_event_out(e, stages, reasons, users) for e in events],
    )


# --- Кросс-оценки --------------------------------------------------------------------

_FORMAL_RANK = {CheckResult.MET: 0, CheckResult.UNKNOWN: 1, CheckResult.NOT_MET: 2}


def cross_assessments(session: Session, candidate_id: uuid.UUID) -> CrossAssessmentListOut:
    """Оценки кандидата по всем должностям с утверждённым профилем в его контуре.

    Контур задаёт кандидат, как в карточке отклика: учебного — учебные профили,
    реального — рабочие. Статус считает тот же resolve_states(), что список и карточка.
    Для каждой вакансии должности отдельно видно, есть ли у кандидата отклик на неё.
    Чтение ничего не создаёт: ни оценок, ни откликов.
    """
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise not_found("CANDIDATE_NOT_FOUND", "Кандидат не найден", candidate_id=candidate_id)
    synthetic = candidate.is_synthetic

    profiles = session.execute(
        select(RequirementProfile, Position)
        .join(Position, Position.id == RequirementProfile.position_id)
        .where(RequirementProfile.status == RequirementStatus.APPROVED, RequirementProfile.is_synthetic == synthetic)
        .order_by(Position.code)
    ).all()
    position_ids = [position.id for _, position in profiles]
    vacancies: dict[uuid.UUID, list[Vacancy]] = {}
    if position_ids:
        for vacancy in session.scalars(
            select(Vacancy).where(Vacancy.position_id.in_(position_ids)).order_by(Vacancy.title, Vacancy.id)
        ):
            vacancies.setdefault(vacancy.position_id, []).append(vacancy)
    applied = {
        application.vacancy_id: (application, stage)
        for application, stage in session.execute(
            select(Application, SelectionStage)
            .join(SelectionStage, SelectionStage.code == Application.current_stage_code)
            .where(Application.candidate_id == candidate.id, Application.vacancy_id.is_not(None))
        ).all()
    }

    items = []
    for profile, position in profiles:
        state = services.resolve_states(session, [candidate.id], profile, position.id, synthetic)[candidate.id]
        assessment = state.assessment
        vacancy_rows = []
        for vacancy in vacancies.get(position.id, []):
            application, stage = applied.get(vacancy.id, (None, None))
            vacancy_rows.append(CrossVacancyOut(
                vacancy_id=vacancy.id, title=vacancy.title, channel=vacancy.channel, status=vacancy.status,
                application_id=application.id if application else None,
                application_source=application.source if application else None,
                application_stage=stage_out(stage) if stage else None,
            ))
        items.append(
            CrossAssessmentItemOut(
                position_id=position.id,
                position_code=position.code,
                position_title=position.title,
                is_municipal_service=position.is_municipal_service,
                approved_profile_id=profile.id,
                approved_profile_version=profile.version,
                is_training=repo.is_training_assessment(candidate, profile),
                assessment_status=state.status,
                formal_result=assessment.formal_result if assessment else None,
                formal_preliminary=assessment.formal_preliminary if assessment else None,
                overall_score=assessment.overall_score if assessment else None,
                has_application=any(v.application_id for v in vacancy_rows),
                vacancies=vacancy_rows,
                assessment=services.assessment_out(session, candidate, state) if assessment else None,
            )
        )
    # Сначала оценённые: допуск выполнен → нет сведений → не выполнен, внутри — по баллу.
    items.sort(key=lambda i: (
        i.assessment is None,
        _FORMAL_RANK.get(i.formal_result, 3),
        -(i.overall_score if i.overall_score is not None else -1),
        i.position_code,
    ))
    return CrossAssessmentListOut(
        candidate_id=candidate.id, candidate_code=candidate.code, is_training=synthetic, items=items
    )


# --- Кадровый резерв -----------------------------------------------------------------

def _headlines(session: Session, candidates: list[Candidate]) -> dict[uuid.UUID, str | None]:
    """Заголовок кандидата: из кандидата, иначе из текущей карточки (как в списке откликов)."""
    missing = [c.id for c in candidates if not c.headline]
    cards = {}
    if missing:
        cards = {
            card.candidate_id: card.card.get("headline")
            for card in session.scalars(
                select(CandidateCard).where(CandidateCard.candidate_id.in_(missing), CandidateCard.is_current)
            )
        }
    return {c.id: c.headline or cards.get(c.id) for c in candidates}


def _reserve_out(entry: ReserveEntry, candidate: Candidate, headline: str | None, users: dict[uuid.UUID, User]) -> ReserveEntryOut:
    return ReserveEntryOut(
        reserve_id=entry.id,
        candidate_id=candidate.id,
        candidate_code=candidate.code,
        headline=headline,
        is_training=candidate.is_synthetic,
        position_id=entry.position_id,
        competency_area=entry.competency_area,
        source_application_id=entry.source_application_id,
        reason=entry.reason,
        contact_basis=entry.contact_basis,
        status=entry.status,
        added_by=user_out(users.get(entry.added_by_user_id)),
        added_at=entry.added_at,
        valid_until=entry.valid_until,
        ended_at=entry.ended_at,
        end_reason=entry.end_reason,
        ended_by=user_out(users.get(entry.ended_by_user_id)),
    )


def _entry_out(session: Session, entry: ReserveEntry) -> ReserveEntryOut:
    candidate = session.get(Candidate, entry.candidate_id)
    users = _users(session, [entry.added_by_user_id, entry.ended_by_user_id])
    return _reserve_out(entry, candidate, _headlines(session, [candidate])[candidate.id], users)


def add_to_reserve(session: Session, body: ReserveIn, user: User, *, today: date | None = None) -> ReserveCreatedOut:
    """Включить в резерв по явному решению кадровика.

    Обоснование (reason) и основание повторного контакта (contact_basis) обязательны: без них
    запись не создаётся. Повтор на ту же цель, в том числе одновременный, возвращает прежнюю
    действующую запись (created = false); истёкшая запись закрывается, и открывается новый период.
    """
    today = today or repo.moscow_today()
    candidate = session.get(Candidate, body.candidate_id)
    if candidate is None:
        raise not_found("CANDIDATE_NOT_FOUND", "Кандидат не найден", candidate_id=body.candidate_id)
    if body.position_id is not None and session.get(Position, body.position_id) is None:
        raise not_found("POSITION_NOT_FOUND", "Должность не найдена", position_id=body.position_id)
    area = _clean(body.competency_area)
    if body.position_id is None and area is None:
        raise ApiError(422, "RESERVE_TARGET_REQUIRED", "Укажите должность (position_id) или направление (competency_area)")
    reason, contact_basis = _clean(body.reason), _clean(body.contact_basis)
    missing = [name for name, value in (("reason", reason), ("contact_basis", contact_basis)) if value is None]
    if missing:
        raise ApiError(422, "RESERVE_BASIS_REQUIRED",
                       "Укажите обоснование пригодности и основание повторного контакта", {"missing": missing})
    if body.valid_until is not None and body.valid_until < today:
        raise ApiError(422, "RESERVE_VALID_UNTIL_IN_PAST", "Срок резерва уже прошёл",
                       {"valid_until": body.valid_until.isoformat()})
    if body.source_application_id is not None:
        source = get_application_or_404(session, body.source_application_id)
        if source.candidate_id != candidate.id:
            raise ApiError(422, "APPLICATION_OF_OTHER_CANDIDATE", "Исходный отклик принадлежит другому кандидату",
                           {"source_application_id": str(source.id)})
        require_working_application(source)

    entry, created = repo.reserve_candidate(
        session,
        candidate_id=candidate.id,
        position_id=body.position_id,
        competency_area=area,
        source_application_id=body.source_application_id,
        reason=reason,
        contact_basis=contact_basis,
        added_by_user_id=user.id,
        valid_until=body.valid_until,
        today=today,
    )
    session.commit()
    session.refresh(entry)
    return ReserveCreatedOut(created=created, entry=_entry_out(session, entry))


def withdraw_reserve(session: Session, reserve_id: uuid.UUID, body: ReserveWithdrawIn, user: User) -> ReserveEntryOut:
    """Отозвать основание резерва: запись пропадает из списка и фильтра поиска, но остаётся в истории."""
    entry = session.get(ReserveEntry, reserve_id)
    if entry is None:
        raise not_found("RESERVE_NOT_FOUND", "Запись резерва не найдена", reserve_id=reserve_id)
    if _clean(body.reason) is None:
        raise ApiError(422, "WITHDRAW_REASON_REQUIRED", "Укажите, почему основание резерва отозвано")
    if entry.status != ReserveStatus.ACTIVE:
        raise ApiError(409, "RESERVE_NOT_ACTIVE", "Запись резерва уже не активна", {"status": str(entry.status)})
    entry = repo.withdraw_reserve(session, entry.id, actor_user_id=user.id, reason=body.reason)
    session.commit()
    return _entry_out(session, entry)


def list_reserve(session: Session, position_id: uuid.UUID, contour: Contour, *, today: date | None = None) -> ReserveListOut:
    position = session.get(Position, position_id)
    if position is None:
        raise not_found("POSITION_NOT_FOUND", "Должность не найдена", position_id=position_id)
    synthetic = contour == Contour.TRAINING
    entries = repo.reserve_for_position(session, position.id, today=today)
    candidates = {c.id: c for c in session.scalars(
        select(Candidate).where(Candidate.id.in_({e.candidate_id for e in entries}))
    )} if entries else {}
    entries = [e for e in entries if candidates[e.candidate_id].is_synthetic == synthetic]
    headlines = _headlines(session, list(candidates.values()))
    users = _users(session, [u for e in entries for u in (e.added_by_user_id, e.ended_by_user_id)])
    items = [_reserve_out(e, candidates[e.candidate_id], headlines[e.candidate_id], users) for e in entries]
    return ReserveListOut(position_id=position.id, position_code=position.code, total=len(items), items=items)


# --- Воронка -----------------------------------------------------------------------------

def period_bounds(period_from: date | None, period_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Даты периода включительно → полуинтервал [начало period_from; начало дня после period_to) по МСК."""
    start = datetime.combine(period_from, time.min, REPORT_TZ) if period_from else None
    end = datetime.combine(period_to + timedelta(days=1), time.min, REPORT_TZ) if period_to else None
    return start, end


def funnel(
    session: Session,
    contour: Contour,
    vacancy_id: uuid.UUID | None,
    position_id: uuid.UUID | None,
    period_from: date | None,
    period_to: date | None,
) -> FunnelOut:
    """Сводка для руководителя по фактическим записям базы.

    Выборка: отклики площадки (source = response, БД v1.6) кандидатов выбранного контура
    на вакансии платформы, с фильтром по вакансии или должности.
    - as_of — момент среза (время ответа сервера, UTC);
    - stages: current_count — уникальные отклики, которые сейчас на этапе;
      reached_count — разные отклики, у которых есть переход на этап (stage_events);
    - closures: решения о закрытии (переход в «Принят», «Отказ», «Кандидат отказался»)
      за период по времени события, с причиной; без причины — отдельная строка «не указана»;
    - open_waits: ожидания ответа считает workflow-01 по передачам; до него — null.
    """
    if vacancy_id is not None and session.get(Vacancy, vacancy_id) is None:
        raise not_found("VACANCY_NOT_FOUND", "Вакансия не найдена", vacancy_id=vacancy_id)
    if position_id is not None and session.get(Position, position_id) is None:
        raise not_found("POSITION_NOT_FOUND", "Должность не найдена", position_id=position_id)
    if period_from and period_to and period_from > period_to:
        raise ApiError(422, "INVALID_PERIOD", "Начало периода позже конца",
                       {"period_from": period_from.isoformat(), "period_to": period_to.isoformat()})

    as_of = datetime.now(timezone.utc)
    scope = (
        select(Application.id, Application.current_stage_code)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(Application.source == ApplicationSource.RESPONSE,
               Candidate.is_synthetic == (contour == Contour.TRAINING))
    )
    if vacancy_id is not None:
        scope = scope.where(Application.vacancy_id == vacancy_id)
    if position_id is not None:
        scope = scope.where(Vacancy.position_id == position_id)
    rows = session.execute(scope).all()
    scope_ids = scope.with_only_columns(Application.id).scalar_subquery()

    current = Counter(code for _, code in rows)
    reached = dict(
        session.execute(
            select(StageEvent.to_stage_code, func.count(func.distinct(StageEvent.application_id)))
            .where(StageEvent.application_id.in_(scope_ids))
            .group_by(StageEvent.to_stage_code)
        ).all()
    )
    stage_rows = list(session.scalars(select(SelectionStage).order_by(SelectionStage.sort_order)))
    stages = [
        FunnelStageOut(code=s.code, title=s.title, sort_order=s.sort_order, is_final=s.is_final,
                       current_count=current.get(s.code, 0), reached_count=reached.get(s.code, 0))
        for s in stage_rows
    ]

    start, end = period_bounds(period_from, period_to)
    closing = (
        select(StageEvent.to_stage_code, StageEvent.rejection_reason_code, func.count())
        .where(StageEvent.application_id.in_(scope_ids), StageEvent.to_stage_code.in_(CLOSING_STAGES))
        .group_by(StageEvent.to_stage_code, StageEvent.rejection_reason_code)
    )
    if start is not None:
        closing = closing.where(StageEvent.created_at >= start)
    if end is not None:
        closing = closing.where(StageEvent.created_at < end)
    stage_by_code = {s.code: s for s in stage_rows}
    reasons = _reasons(session)
    closures = []
    for stage_code, reason_code, count in session.execute(closing).all():
        reason = reasons.get(reason_code) if reason_code else None
        if reason is not None:
            title = reason.title
        else:
            title = "—" if stage_code == "hired" else "Причина не указана"
        closures.append(FunnelClosureOut(
            stage_code=stage_code,
            stage_title=stage_by_code[stage_code].title,
            reason_code=reason_code,
            reason_title=title,
            side=reason.side if reason else None,
            count=count,
        ))
    closures.sort(key=lambda c: (stage_by_code[c.stage_code].sort_order, c.reason_code is None, c.reason_code or ""))

    return FunnelOut(
        as_of=as_of,
        contour=contour,
        vacancy_id=vacancy_id,
        position_id=position_id,
        period_from=period_from,
        period_to=period_to,
        timezone=str(REPORT_TZ),
        total_applications=len(rows),
        stages=stages,
        closures=closures,
        closures_without_reason=sum(c.count for c in closures if c.reason_code is None and c.stage_code != "hired"),
        open_waits=None,
    )
