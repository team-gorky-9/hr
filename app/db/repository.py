"""Функции доступа к данным: ими пользуются импорт, ИИ-модуль, поиск и API.

Каждая функция работает внутри переданной сессии и не делает commit: транзакцией
управляет вызывающий (скрипт импорта, обработчик запроса), чтобы несколько шагов
сохранялись вместе или не сохранялись вовсе. Ошибки бизнес-правил — исключения
из этого модуля с понятным текстом; они не проглатываются.
"""
import hashlib
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import PurePath
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import (
    ApplicationSource,
    AuditAction,
    Channel,
    CheckResult,
    CheckStage,
    DocumentKind,
    FeedbackOutcome,
    FileFormat,
    FormalRequirementKind,
    HandoffChannel,
    HandoffStatus,
    ProcessFactStatus,
    RequirementStatus,
    ReserveStatus,
    UserRole,
    VerificationMethod,
)
from app.db.models import (
    Application,
    Assessment,
    AuditLog,
    Candidate,
    CandidateCard,
    CandidatePii,
    CandidateSkill,
    CandidateText,
    Competency,
    CompetencyIndicator,
    CompetencyScore,
    DepartmentFeedback,
    FormalCheck,
    FormalRequirement,
    HandoffAttempt,
    Position,
    ProfileSource,
    RejectionReason,
    RequirementProfile,
    ReserveEntry,
    SelectionStage,
    SourceDocument,
    StageEvent,
    User,
    Vacancy,
)
from app.db.seed import INITIAL_STAGE
from app.schemas.assessment import AlternativeResultIn, CompetencyScoreIn, FormalCheckIn
from app.schemas.card import CandidateCard as CardSchema
from app.schemas.card import Evidence, evidence_matches
from app.schemas.pii import PiiData
from app.schemas.requirements import CompetencyIn, FormalRequirementIn, ProfileSourceIn, alternative_keys


class RepositoryError(Exception):
    """Нарушено правило работы с данными."""


class StageTransitionError(RepositoryError):
    pass


class EvidenceError(RepositoryError):
    pass


class RequestIdReusedError(RepositoryError):
    pass


class FeedbackConflictError(RepositoryError):
    def __init__(self, message: str, *, current_feedback_id: uuid.UUID, current_revision: int):
        super().__init__(message)
        self.current_feedback_id = current_feedback_id
        self.current_revision = current_revision


def _get(session: Session, model, row_id: uuid.UUID, label: str):
    """Найти запись по UUID или сообщить понятной ошибкой."""
    row = session.get(model, row_id)
    if row is None:
        raise RepositoryError(f"нет записи «{label}» с id {row_id}")
    return row


# --- Источники ---------------------------------------------------------------

def add_source_document(
    session: Session,
    *,
    kind: DocumentKind,
    channel: Channel,
    file_format: FileFormat,
    original_path: str,
    raw_text: str,
    content: bytes | None = None,
    import_batch: str | None = None,
) -> tuple[SourceDocument, bool]:
    """Сохранить исходный документ. Возвращает (документ, создан_ли_новый).

    Дубль определяется по SHA-256 содержимого файла (content), а если его не передали —
    по тексту. Повторный импорт того же файла вернёт уже сохранённый документ.
    """
    digest = hashlib.sha256(content if content is not None else raw_text.encode("utf-8")).hexdigest()
    existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == digest))
    if existing is not None:
        return existing, False

    # Имена в архиве организаторов в Unicode NFD (macOS): «й» хранится как «и» + знак.
    path = unicodedata.normalize("NFC", original_path)
    document = SourceDocument(
        kind=kind,
        channel=channel,
        file_format=file_format,
        original_path=path,
        file_name=PurePath(path.replace("\\", "/")).name,
        sha256=digest,
        raw_text=raw_text,
        import_batch=import_batch,
    )
    session.add(document)
    session.flush()
    return document, True


# --- Кандидат ----------------------------------------------------------------

def create_candidate(
    session: Session,
    *,
    code: str,
    source_document_id: uuid.UUID,
    redacted_text: str,
    redaction_method: str,
    headline: str | None = None,
    pii: PiiData | None = None,
    is_synthetic: bool = False,
) -> Candidate:
    """Создать кандидата из резюме: запись кандидата, его ПДн и первую версию очищенного текста.

    is_synthetic = True — учебный кандидат (выдуманный текст, py-9001): он в учебном контуре
    и не попадает в рабочие списки. Признак после создания не меняется.
    """
    source_document = _get(session, SourceDocument, source_document_id, "исходный документ")
    if source_document.kind != DocumentKind.RESUME:
        raise RepositoryError(f"документ {source_document.original_path} не резюме: {source_document.kind}")

    candidate = Candidate(
        code=code, source_document_id=source_document.id, headline=headline, is_synthetic=is_synthetic
    )
    session.add(candidate)
    session.flush()
    if pii is not None:
        session.add(CandidatePii(candidate_id=candidate.id, **pii.model_dump()))
    session.add(
        CandidateText(
            candidate_id=candidate.id,
            version=1,
            is_current=True,
            redaction_method=redaction_method,
            text=redacted_text,
        )
    )
    session.flush()
    return candidate


def get_current_text(session: Session, candidate_id: uuid.UUID) -> CandidateText | None:
    return session.scalar(
        select(CandidateText).where(CandidateText.candidate_id == candidate_id, CandidateText.is_current)
    )


def add_candidate_text(
    session: Session, candidate_id: uuid.UUID, *, text: str, redaction_method: str
) -> CandidateText:
    """Новая версия очищенного текста (например, улучшили очистку). Старая перестаёт быть текущей."""
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    version = _next_version(session, CandidateText.version, CandidateText.candidate_id == candidate.id)
    _clear_current(session, CandidateText, CandidateText.candidate_id == candidate.id)
    row = CandidateText(
        candidate_id=candidate.id,
        version=version,
        is_current=True,
        redaction_method=redaction_method,
        text=text,
    )
    session.add(row)
    session.flush()
    return row


def add_candidate_card(
    session: Session,
    candidate_id: uuid.UUID,
    card: CardSchema,
    *,
    extractor: str,
    prompt_version: str | None = None,
    candidate_text_id: uuid.UUID | None = None,
) -> CandidateCard:
    """Сохранить новую версию карточки и навыки из неё. Предыдущая версия остаётся в истории."""
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    if candidate_text_id is not None:
        text_row = _get(session, CandidateText, candidate_text_id, "очищенный текст")
    else:
        text_row = get_current_text(session, candidate.id)
    if text_row is None:
        raise RepositoryError(f"у кандидата {candidate.code} нет очищенного текста")
    if text_row.candidate_id != candidate.id:
        raise RepositoryError("текст принадлежит другому кандидату")

    version = _next_version(session, CandidateCard.version, CandidateCard.candidate_id == candidate.id)
    _clear_current(session, CandidateCard, CandidateCard.candidate_id == candidate.id)

    row = CandidateCard(
        candidate_id=candidate.id,
        candidate_text_id=text_row.id,
        version=version,
        is_current=True,
        extractor=extractor,
        prompt_version=prompt_version,
        card=card.model_dump(mode="json"),
        experience_years=card.experience_years,
        education_level=card.education[0].level if card.education else None,
        missing_count=len(card.missing),
    )
    session.add(row)
    session.flush()

    seen: set[str] = set()
    for skill in card.skills:
        key = normalize_skill(skill.name)
        if not key or key in seen:
            continue
        seen.add(key)
        session.add(
            CandidateSkill(
                card_id=row.id, candidate_id=candidate.id, name=skill.name, normalized=key, level=skill.level
            )
        )
    session.flush()
    return row


def get_current_card(session: Session, candidate_id: uuid.UUID) -> CandidateCard | None:
    return session.scalar(
        select(CandidateCard).where(CandidateCard.candidate_id == candidate_id, CandidateCard.is_current)
    )


def normalize_skill(name: str) -> str:
    """«  Post­greSQL » → «postgresql»: регистр, ё/е, лишние пробелы."""
    cleaned = unicodedata.normalize("NFKC", name).replace("­", "")
    return " ".join(cleaned.lower().replace("ё", "е").split())


def find_candidates_by_skills(
    session: Session, skills: Iterable[str], *, match_all: bool = True
) -> list[Candidate]:
    """Кандидаты, у которых в текущей карточке есть все (или хотя бы один) из навыков."""
    keys = sorted({normalize_skill(s) for s in skills} - {""})
    if not keys:
        return []
    matched = (
        select(CandidateSkill.candidate_id)
        .join(CandidateCard, CandidateCard.id == CandidateSkill.card_id)
        .where(CandidateCard.is_current, CandidateSkill.normalized.in_(keys))
        .group_by(CandidateSkill.candidate_id)
    )
    if match_all:
        matched = matched.having(func.count(func.distinct(CandidateSkill.normalized)) == len(keys))
    return list(session.scalars(select(Candidate).where(Candidate.id.in_(matched)).order_by(Candidate.code)))


# --- Персональные данные и аудит ---------------------------------------------

def get_candidate_pii(
    session: Session, candidate_id: uuid.UUID, *, user_id: uuid.UUID | None, purpose: str
) -> CandidatePii | None:
    """Открыть ПДн кандидата. Каждое обращение пишется в журнал с целью."""
    write_audit(
        session,
        action=AuditAction.VIEW_PII,
        entity_type="candidate",
        entity_id=str(candidate_id),
        user_id=user_id,
        details={"purpose": purpose},
    )
    return session.get(CandidatePii, candidate_id)


def write_audit(
    session: Session,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: str | None = None,
    user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}
    )
    session.add(entry)
    session.flush()
    return entry


# --- Отбор -------------------------------------------------------------------

def create_application(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    source: ApplicationSource,
    vacancy_id: uuid.UUID | None = None,
    external_position_title: str | None = None,
    applied_at: date | None = None,
    actor_user_id: uuid.UUID | None = None,
    posting_title: str | None = None,
) -> Application:
    """Начать отбор кандидата на вакансию. Первый этап — «Новый отклик», он же пишется в журнал."""
    if vacancy_id is None and not external_position_title:
        raise RepositoryError("нужна вакансия или название внешней должности")
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    if vacancy_id is not None:
        _get(session, Vacancy, vacancy_id, "вакансия")

    application = Application(
        candidate_id=candidate.id,
        vacancy_id=vacancy_id,
        external_position_title=external_position_title,
        source=source,
        applied_at=applied_at,
        posting_title=posting_title,
        current_stage_code=INITIAL_STAGE,
    )
    session.add(application)
    session.flush()
    session.add(
        StageEvent(application_id=application.id, from_stage_code=None, to_stage_code=INITIAL_STAGE,
                   actor_user_id=actor_user_id)
    )
    session.flush()
    return application


def move_application(
    session: Session,
    application_id: uuid.UUID,
    to_stage_code: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    comment: str | None = None,
    rejection_reason_code: str | None = None,
    confirm_skip: bool = False,
) -> StageEvent:
    """Перевести отклик на другой этап. Меняет текущий этап и пишет событие в журнал одним шагом.

    Правила: из финального этапа (принят, отказ, кандидат отказался) переходов нет;
    причина отказа указывается только при переходе в «Отказ» или «Кандидат отказался».
    Обычный шаг — на следующий этап по порядку, в «Отказ» или «Кандидат отказался» в любой
    момент, в «Принят» — с последнего этапа. Остальное (перескок вперёд, возврат назад)
    — только с подтверждением человека: confirm_skip=True, actor_user_id и comment.
    """
    # Блокируем строку отклика: два кадровика не переведут его одновременно в разные этапы.
    application = session.get(Application, application_id, with_for_update=True)
    if application is None:
        raise StageTransitionError(f"нет отклика с id {application_id}")
    current = session.get(SelectionStage, application.current_stage_code)
    target = session.get(SelectionStage, to_stage_code)
    if target is None:
        raise StageTransitionError(f"нет этапа «{to_stage_code}»")
    if current.is_final:
        raise StageTransitionError(f"отбор уже завершён на этапе «{current.title}»")
    if target.code == current.code:
        raise StageTransitionError(f"отклик уже на этапе «{current.title}»")
    if not _is_regular_step(session, current, target):
        if not (confirm_skip and actor_user_id is not None and comment and comment.strip()):
            raise StageTransitionError(
                f"переход «{current.title}» → «{target.title}» идёт не по порядку этапов: "
                "нужно подтверждение человека (confirm_skip, actor_user_id и comment с причиной)"
            )
    if rejection_reason_code is not None:
        if target.code not in EXIT_STAGES:
            raise StageTransitionError("причина отказа указывается только при отказе")
        if session.get(RejectionReason, rejection_reason_code) is None:
            raise StageTransitionError(f"нет причины отказа «{rejection_reason_code}»")

    event = StageEvent(
        application_id=application.id,
        from_stage_code=current.code,
        to_stage_code=target.code,
        rejection_reason_code=rejection_reason_code,
        actor_user_id=actor_user_id,
        comment=comment,
    )
    application.current_stage_code = target.code
    session.add(event)
    session.flush()
    return event


EXIT_STAGES = ("rejected", "withdrawn")


def _is_regular_step(session: Session, current: SelectionStage, target: SelectionStage) -> bool:
    """Шаг по порядку: следующий нефинальный этап, выход из отбора или финал с последнего этапа."""
    if target.code in EXIT_STAGES:
        return True
    following = session.scalars(
        select(SelectionStage)
        .where(SelectionStage.sort_order > current.sort_order, SelectionStage.is_final.is_(False))
        .order_by(SelectionStage.sort_order)
    ).first()
    if target.is_final:
        return following is None
    return following is not None and following.code == target.code


def stage_history(session: Session, application_id: uuid.UUID) -> list[StageEvent]:
    return list(
        session.scalars(
            select(StageEvent).where(StageEvent.application_id == application_id).order_by(StageEvent.seq)
        )
    )


def record_department_feedback(
    session: Session,
    application_id: uuid.UUID,
    *,
    outcome: FeedbackOutcome,
    interview_held: bool | None = None,
    interview_status: ProcessFactStatus | None = None,
    contact_status: ProcessFactStatus = ProcessFactStatus.NOT_REPORTED,
    confirmed_competencies: Sequence[str] = (),
    gaps: str | None = None,
    rejection_reason_code: str | None = None,
    keep_in_reserve: bool | None = None,
    comment: str | None = None,
    author_user_id: uuid.UUID | None = None,
) -> DepartmentFeedback:
    """Сохранить обратную связь департамента. Этап отклика не меняется сам:
    решение о следующем шаге принимает кадровик (move_application)."""
    application = _get(session, Application, application_id, "отклик")
    if rejection_reason_code is not None and session.get(RejectionReason, rejection_reason_code) is None:
        raise RepositoryError(f"нет причины отказа «{rejection_reason_code}»")
    if interview_status is None:
        if interview_held is True:
            interview_status = ProcessFactStatus.YES
        elif interview_held is False:
            interview_status = ProcessFactStatus.NO
        else:
            interview_status = ProcessFactStatus.NOT_REPORTED
    feedback = DepartmentFeedback(
        application_id=application.id,
        interview_held=interview_held,
        interview_status=interview_status,
        contact_status=contact_status,
        outcome=outcome,
        confirmed_competencies=list(confirmed_competencies),
        gaps=gaps,
        rejection_reason_code=rejection_reason_code,
        keep_in_reserve=keep_in_reserve,
        comment=comment,
        author_user_id=author_user_id,
    )
    session.add(feedback)
    session.flush()
    return feedback


def _handoff_matches(
    existing: HandoffAttempt,
    *,
    application_id: uuid.UUID,
    recipient_user_id: uuid.UUID | None,
    recipient_name: str,
    recipient_department: str,
    channel: HandoffChannel,
    summary_revision: str,
) -> bool:
    return (
        existing.application_id == application_id
        and existing.recipient_user_id == recipient_user_id
        and existing.recipient_name == recipient_name
        and existing.recipient_department == recipient_department
        and existing.channel == channel
        and existing.summary_revision == summary_revision
    )


def create_handoff_attempt(
    session: Session,
    *,
    application_id: uuid.UUID,
    stage_event_id: uuid.UUID | None,
    recipient_user_id: uuid.UUID | None,
    recipient_name: str,
    recipient_department: str,
    channel: HandoffChannel,
    handed_off_at: datetime,
    created_by_user_id: uuid.UUID | None,
    summary_revision: str,
    summary_snapshot: dict[str, Any],
    request_id: uuid.UUID | None = None,
) -> tuple[HandoffAttempt, bool]:
    """Создать попытку передачи отклика получателю с замороженным снимком сводки.

    Повтор с тем же request_id и теми же полями возвращает существующую попытку (created = False);
    использование того же request_id для другой передачи отклоняется RequestIdReusedError.
    """
    _get(session, Application, application_id, "отклик")
    if request_id is not None:
        existing = session.scalar(select(HandoffAttempt).where(HandoffAttempt.request_id == request_id))
        if existing is not None:
            if _handoff_matches(
                existing,
                application_id=application_id,
                recipient_user_id=recipient_user_id,
                recipient_name=recipient_name,
                recipient_department=recipient_department,
                channel=channel,
                summary_revision=summary_revision,
            ):
                return existing, False
            raise RequestIdReusedError("request_id уже использован для другой передачи")

    attempt = HandoffAttempt(
        application_id=application_id,
        stage_event_id=stage_event_id,
        recipient_user_id=recipient_user_id,
        recipient_name=recipient_name,
        recipient_department=recipient_department,
        channel=channel,
        handed_off_at=handed_off_at,
        created_by_user_id=created_by_user_id,
        summary_revision=summary_revision,
        summary_snapshot=summary_snapshot,
        status=HandoffStatus.AWAITING_RESPONSE,
        request_id=request_id,
    )
    savepoint = session.begin_nested()
    try:
        session.add(attempt)
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        if request_id is not None:
            existing = session.scalar(select(HandoffAttempt).where(HandoffAttempt.request_id == request_id))
            if existing is not None:
                if _handoff_matches(
                    existing,
                    application_id=application_id,
                    recipient_user_id=recipient_user_id,
                    recipient_name=recipient_name,
                    recipient_department=recipient_department,
                    channel=channel,
                    summary_revision=summary_revision,
                ):
                    return existing, False
                raise RequestIdReusedError("request_id уже использован для другой передачи")
        raise
    savepoint.commit()
    session.refresh(attempt)
    return attempt, True


def close_open_handoffs_for_application(
    session: Session,
    application_id: uuid.UUID,
    *,
    closed_at: datetime,
    close_reason: str,
    stage_event_id: uuid.UUID | None,
) -> int:
    """Закрыть все незавершённые ожидания отклика при уходе с этапа передачи."""
    open_attempts = list(
        session.scalars(
            select(HandoffAttempt).where(
                HandoffAttempt.application_id == application_id,
                HandoffAttempt.status == HandoffStatus.AWAITING_RESPONSE,
            )
        )
    )
    for attempt in open_attempts:
        attempt.status = HandoffStatus.CLOSED_WITHOUT_RESPONSE
        attempt.closed_at = closed_at
        attempt.close_reason = close_reason
        attempt.closed_by_stage_event_id = stage_event_id
    if open_attempts:
        session.flush()
    return len(open_attempts)


def _feedback_matches(
    existing: DepartmentFeedback,
    *,
    application_id: uuid.UUID,
    attempt_id: uuid.UUID,
    supersedes_id: uuid.UUID | None,
    outcome: FeedbackOutcome,
    contact_status: ProcessFactStatus,
    interview_status: ProcessFactStatus,
    rejection_reason_code: str | None,
    keep_in_reserve: bool | None,
    comment: str | None,
    gaps: str | None,
    confirmed_competencies: Sequence[str],
    response_channel: HandoffChannel | None,
    reported_by_user_id: uuid.UUID | None,
    reported_by_name: str | None,
) -> bool:
    return (
        existing.application_id == application_id
        and existing.attempt_id == attempt_id
        and existing.supersedes_id == supersedes_id
        and existing.outcome == outcome
        and existing.contact_status == contact_status
        and existing.interview_status == interview_status
        and existing.rejection_reason_code == rejection_reason_code
        and existing.keep_in_reserve == keep_in_reserve
        and existing.comment == comment
        and existing.gaps == gaps
        and list(existing.confirmed_competencies or []) == list(confirmed_competencies)
        and existing.response_channel == response_channel
        and existing.reported_by_user_id == reported_by_user_id
        and existing.reported_by_name == reported_by_name
    )


def record_handoff_feedback(
    session: Session,
    *,
    application_id: uuid.UUID,
    attempt_id: uuid.UUID,
    outcome: FeedbackOutcome,
    contact_status: ProcessFactStatus,
    interview_status: ProcessFactStatus,
    confirmed_competencies: Sequence[str] = (),
    gaps: str | None = None,
    rejection_reason_code: str | None = None,
    keep_in_reserve: bool | None = None,
    comment: str | None = None,
    response_channel: HandoffChannel | None = None,
    reported_by_user_id: uuid.UUID | None = None,
    reported_by_name: str | None = None,
    reported_at: datetime | None = None,
    author_user_id: uuid.UUID | None = None,
    supersedes_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
) -> tuple[DepartmentFeedback, bool]:
    """Записать ответ департамента или его исправление по конкретной попытке передачи.

    Управляет статусом ожидания только этой попытки. Этап отклика и резерв не меняет.
    """
    application = _get(session, Application, application_id, "отклик")
    if rejection_reason_code is not None and session.get(RejectionReason, rejection_reason_code) is None:
        raise RepositoryError(f"нет причины отказа «{rejection_reason_code}»")

    competencies_list = list(confirmed_competencies)
    if request_id is not None:
        existing = session.scalar(select(DepartmentFeedback).where(DepartmentFeedback.request_id == request_id))
        if existing is not None:
            if _feedback_matches(
                existing,
                application_id=application_id,
                attempt_id=attempt_id,
                supersedes_id=supersedes_id,
                outcome=outcome,
                contact_status=contact_status,
                interview_status=interview_status,
                rejection_reason_code=rejection_reason_code,
                keep_in_reserve=keep_in_reserve,
                comment=comment,
                gaps=gaps,
                confirmed_competencies=competencies_list,
                response_channel=response_channel,
                reported_by_user_id=reported_by_user_id,
                reported_by_name=reported_by_name,
            ):
                return existing, False
            raise RequestIdReusedError("request_id уже использован для другого отзыва")

    # Блокируем попытку передачи, чтобы две конкурирующие правки одной версии не прошли вместе.
    attempt = session.get(HandoffAttempt, attempt_id, with_for_update=True)
    if attempt is None:
        raise RepositoryError(f"нет передачи с id {attempt_id}")
    if attempt.application_id != application.id:
        raise RepositoryError("передача относится к другому отклику")

    existing_rows = list(
        session.scalars(
            select(DepartmentFeedback)
            .where(DepartmentFeedback.attempt_id == attempt.id)
            .order_by(DepartmentFeedback.revision)
        )
    )
    if supersedes_id is None:
        if existing_rows:
            latest = existing_rows[-1]
            raise FeedbackConflictError(
                "по этой передаче уже записан отзыв: для исправления укажите supersedes_id текущей версии",
                current_feedback_id=latest.id,
                current_revision=latest.revision,
            )
        revision = 1
    else:
        prev = next((row for row in existing_rows if row.id == supersedes_id), None)
        if prev is None:
            raise RepositoryError("исправляемый отзыв не относится к этой передаче или не найден")
        if any(row.supersedes_id == prev.id for row in existing_rows):
            latest = existing_rows[-1]
            raise FeedbackConflictError(
                "указанная версия отзыва уже исправлена",
                current_feedback_id=latest.id,
                current_revision=latest.revision,
            )
        revision = prev.revision + 1

    interview_held = (
        True
        if interview_status == ProcessFactStatus.YES
        else False
        if interview_status == ProcessFactStatus.NO
        else None
    )
    feedback = DepartmentFeedback(
        application_id=application.id,
        attempt_id=attempt.id,
        supersedes_id=supersedes_id,
        revision=revision,
        contact_status=contact_status,
        interview_status=interview_status,
        interview_held=interview_held,
        outcome=outcome,
        confirmed_competencies=competencies_list,
        gaps=gaps,
        rejection_reason_code=rejection_reason_code,
        keep_in_reserve=keep_in_reserve,
        comment=comment,
        response_channel=response_channel,
        reported_by_user_id=reported_by_user_id,
        reported_by_name=reported_by_name,
        reported_at=reported_at,
        author_user_id=author_user_id,
        request_id=request_id,
    )
    savepoint = session.begin_nested()
    try:
        session.add(feedback)
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        if request_id is not None:
            existing = session.scalar(select(DepartmentFeedback).where(DepartmentFeedback.request_id == request_id))
            if existing is not None:
                if _feedback_matches(
                    existing,
                    application_id=application_id,
                    attempt_id=attempt_id,
                    supersedes_id=supersedes_id,
                    outcome=outcome,
                    contact_status=contact_status,
                    interview_status=interview_status,
                    rejection_reason_code=rejection_reason_code,
                    keep_in_reserve=keep_in_reserve,
                    comment=comment,
                    gaps=gaps,
                    confirmed_competencies=competencies_list,
                    response_channel=response_channel,
                    reported_by_user_id=reported_by_user_id,
                    reported_by_name=reported_by_name,
                ):
                    return existing, False
                raise RequestIdReusedError("request_id уже использован для другого отзыва")
        latest = session.scalar(
            select(DepartmentFeedback)
            .where(DepartmentFeedback.attempt_id == attempt.id)
            .order_by(DepartmentFeedback.revision.desc())
        )
        if latest is not None:
            raise FeedbackConflictError(
                "отзыв уже изменён другим запросом",
                current_feedback_id=latest.id,
                current_revision=latest.revision,
            )
        raise
    savepoint.commit()
    session.refresh(feedback)

    if outcome in (FeedbackOutcome.FIT, FeedbackOutcome.NOT_FIT):
        if attempt.status == HandoffStatus.AWAITING_RESPONSE:
            attempt.status = HandoffStatus.RESPONDED
            attempt.closed_at = feedback.received_at
            attempt.close_reason = f"feedback:{outcome.value}"
        elif attempt.status == HandoffStatus.RESPONDED:
            attempt.close_reason = f"feedback:{outcome.value}"
    elif outcome == FeedbackOutcome.PENDING and attempt.status == HandoffStatus.RESPONDED:
        if application.current_stage_code in ("sent_to_department", "department_interview"):
            attempt.status = HandoffStatus.AWAITING_RESPONSE
            attempt.closed_at = None
            attempt.close_reason = None
    session.flush()
    return feedback, True


def has_department_application_access(session: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> bool:
    """Назначен ли сотрудник департамента получателем хотя бы одной передачи по этому отклику."""
    return (
        session.scalar(
            select(HandoffAttempt.id)
            .where(HandoffAttempt.application_id == application_id, HandoffAttempt.recipient_user_id == user_id)
            .limit(1)
        )
        is not None
    )


def has_department_text_access(session: Session, user_id: uuid.UUID, candidate_text_id: uuid.UUID) -> bool:
    """Упомянут ли очищенный текст в снимке сводки, переданном этому сотруднику департамента."""
    target = str(candidate_text_id)
    snapshots = session.scalars(
        select(HandoffAttempt.summary_snapshot).where(HandoffAttempt.recipient_user_id == user_id)
    )
    return any(target in (snap.get("referenced_text_ids") or ()) for snap in snapshots if snap)


# --- Кадровый резерв ---------------------------------------------------------

RESERVE_TZ = ZoneInfo("Europe/Moscow")


def moscow_today() -> date:
    """Сегодняшняя дата в Нижнем Новгороде (МСК): по ней считается срок резерва."""
    return datetime.now(RESERVE_TZ).date()


def active_reserve_condition(today: date | None = None):
    """Правило «запись резерва действует» — одно для списка резерва и фильтра поиска (search-01):
    статус active и срок не истёк (пустой срок — бессрочно, последний день включён, дата по МСК).
    Запись с истёкшим сроком может ещё стоять в active, пока на ту же цель не открыли новый
    период, но действующей не считается."""
    today = today or moscow_today()
    return (ReserveEntry.status == ReserveStatus.ACTIVE) & or_(
        ReserveEntry.valid_until.is_(None), ReserveEntry.valid_until >= today
    )


def _reserve_target(position_id: uuid.UUID | None, competency_area: str | None):
    """Цель резерва: должность, если указана, иначе направление (так же устроены уникальные индексы)."""
    if position_id is not None:
        return (ReserveEntry.position_id == position_id,)
    return ReserveEntry.position_id.is_(None), ReserveEntry.competency_area == competency_area


def reserve_candidate(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    position_id: uuid.UUID | None = None,
    competency_area: str | None = None,
    source_application_id: uuid.UUID | None = None,
    reason: str | None = None,
    contact_basis: str | None = None,
    added_by_user_id: uuid.UUID | None = None,
    valid_until: date | None = None,
    today: date | None = None,
) -> tuple[ReserveEntry, bool]:
    """Включить кандидата в резерв. Вернуть (запись, создана ли новая).

    - Активная действующая запись на ту же цель уже есть — вернуть её (created = False).
    - Активная, но с истёкшим сроком — закрыть её (expired, ended_at) и открыть новый период
      со своим основанием и происхождением: история прежнего периода сохраняется.
    - Два одновременных запроса: уникальный индекс пропустит одну вставку, вторая получит
      IntegrityError внутри точки сохранения и вернёт запись первой [v1.8].
    - Исходный отклик должен принадлежать этому кандидату и быть откликом площадки
      (source = response): история и ручные записи не основание для резерва [v1.8].
    """
    if position_id is None and not competency_area:
        raise RepositoryError("резерв нужен на должность или на направление")
    today = today or moscow_today()
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    if position_id is not None:
        _get(session, Position, position_id, "должность")
    if source_application_id is not None:
        source = _get(session, Application, source_application_id, "отклик")
        if source.candidate_id != candidate.id:
            raise RepositoryError("исходный отклик принадлежит другому кандидату")
        if source.source != ApplicationSource.RESPONSE:
            raise RepositoryError("основанием резерва может быть только отклик с площадки")

    target = _reserve_target(position_id, competency_area)
    existing = session.scalar(
        select(ReserveEntry)
        .where(ReserveEntry.candidate_id == candidate.id, ReserveEntry.status == ReserveStatus.ACTIVE, *target)
        .with_for_update()
    )
    if existing is not None:
        if existing.valid_until is None or existing.valid_until >= today:
            return existing, False
        existing.status = ReserveStatus.EXPIRED
        existing.ended_at = func.now()
        existing.end_reason = "срок резерва истёк"
        session.flush()

    entry = ReserveEntry(
        candidate_id=candidate.id,
        position_id=position_id,
        competency_area=competency_area,
        source_application_id=source_application_id,
        reason=reason,
        contact_basis=contact_basis,
        added_by_user_id=added_by_user_id,
        valid_until=valid_until,
    )
    savepoint = session.begin_nested()
    try:
        session.add(entry)
        session.flush()
    except IntegrityError:
        # Параллельный запрос успел вставить активную запись на ту же цель.
        savepoint.rollback()
        winner = session.scalar(
            select(ReserveEntry).where(
                ReserveEntry.candidate_id == candidate.id, ReserveEntry.status == ReserveStatus.ACTIVE, *target
            )
        )
        if winner is None:
            raise
        return winner, False
    savepoint.commit()
    return entry, True


def add_to_reserve(session: Session, **kwargs) -> ReserveEntry:
    """Добавить кандидата в резерв без дублей (см. reserve_candidate); вернуть запись."""
    entry, _ = reserve_candidate(session, **kwargs)
    return entry


def withdraw_reserve(
    session: Session, reserve_id: uuid.UUID, *, actor_user_id: uuid.UUID | None, reason: str
) -> ReserveEntry:
    """Отозвать основание: запись перестаёт действовать и остаётся в истории [v1.8]."""
    if not reason or not reason.strip():
        raise RepositoryError("укажите, почему основание резерва отозвано")
    entry = session.get(ReserveEntry, reserve_id, with_for_update=True)
    if entry is None:
        raise RepositoryError(f"нет записи «резерв» с id {reserve_id}")
    if entry.status != ReserveStatus.ACTIVE:
        raise RepositoryError("запись резерва уже не активна")
    entry.status = ReserveStatus.WITHDRAWN
    entry.ended_at = func.now()
    entry.end_reason = reason.strip()
    entry.ended_by_user_id = actor_user_id
    session.flush()
    session.refresh(entry)
    return entry


def reserve_for_position(session: Session, position_id: uuid.UUID, *, today: date | None = None) -> list[ReserveEntry]:
    """Действующий резерв на должность (active_reserve_condition). Резерв «по направлению»
    сюда не входит: его подбирает поиск по смыслу."""
    return list(
        session.scalars(
            select(ReserveEntry)
            .where(ReserveEntry.position_id == position_id, active_reserve_condition(today))
            .order_by(ReserveEntry.added_at)
        )
    )


# --- Требования к должности ------------------------------------------------

def create_requirement_profile(
    session: Session,
    *,
    position_id: uuid.UUID,
    created_by: str,
    formal_requirements: Sequence[FormalRequirementIn],
    competencies: Sequence[CompetencyIn],
    sources: Sequence[ProfileSourceIn] = (),
    version: int | None = None,
    is_synthetic: bool = False,
    note: str | None = None,
) -> RequirementProfile:
    """Создать черновик профиля требований в едином формате.

    Порядок строк сохраняется в sort_order. Документ строки должен быть среди
    источников профиля: так у версии профиля полный и неизменный список документов.
    Версии нумеруются отдельно в рабочем и учебном контуре (is_synthetic): без version
    берётся следующий номер для должности в этом контуре; повтор номера → IntegrityError.
    """
    from app.schemas.requirement_groups import validate_groups
    try:
        validate_groups(competencies)
    except ValueError as error:
        raise RepositoryError(str(error)) from error
    position = _get(session, Position, position_id, "должность")
    source_ids = [s.source_document_id for s in sources]
    if len(set(source_ids)) != len(source_ids):
        raise RepositoryError("документ указан в источниках профиля дважды")
    for document_id in source_ids:
        _get(session, SourceDocument, document_id, "исходный документ")

    rows = [*formal_requirements, *competencies, *(i for c in competencies for i in c.indicators)]
    for row in rows:
        for ref in row.source_refs:
            if ref.source_document_id not in source_ids:
                raise RepositoryError(
                    f"строка {row.key} ссылается на документ {ref.source_document_id}, которого нет в источниках профиля"
                )
    keys = [row.key for row in rows]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise RepositoryError(f"повторяются ключи строк: {', '.join(duplicates)}")
    codes = [c.code for c in competencies]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        raise RepositoryError(f"повторяются коды компетенций: {', '.join(duplicates)}")
    level_keys = {r.key for r in formal_requirements if r.kind == FormalRequirementKind.EDUCATION_LEVEL}
    for requirement in formal_requirements:
        required = requirement.params.get("requires_requirement")
        if required is not None and required not in level_keys:
            raise RepositoryError(
                f"требование {requirement.key} ссылается на {required}: в профиле нет такого требования уровня образования"
            )

    if version is None:
        version = _next_version(
            session,
            RequirementProfile.version,
            RequirementProfile.position_id == position.id,
            RequirementProfile.is_synthetic == is_synthetic,
        )
    profile = RequirementProfile(
        position_id=position.id,
        version=version,
        status=RequirementStatus.DRAFT,
        is_synthetic=is_synthetic,
        created_by=created_by,
        note=note,
    )
    profile.sources = [ProfileSource(**s.model_dump()) for s in sources]
    profile.formal_requirements = [
        FormalRequirement(**_row_fields(r), sort_order=order) for order, r in enumerate(formal_requirements, start=1)
    ]
    profile.competencies = [
        Competency(
            **_row_fields(c, exclude={"indicators"}),
            sort_order=order,
            indicators=[
                CompetencyIndicator(**_row_fields(i), sort_order=i_order)
                for i_order, i in enumerate(c.indicators, start=1)
            ],
        )
        for order, c in enumerate(competencies, start=1)
    ]
    session.add(profile)
    session.flush()
    return profile


def _row_fields(row, exclude: set[str] | None = None) -> dict[str, Any]:
    """Поля строки профиля для модели: JSONB-поля — в JSON-виде (UUID строкой), без пустых критериев."""
    fields = row.model_dump(exclude=exclude)
    fields["source_refs"] = [ref.model_dump(mode="json") for ref in row.source_refs]
    if "acceptance" in fields:
        fields["acceptance"] = row.acceptance.model_dump(exclude_none=True)
    return fields


def approve_requirement_profile(
    session: Session,
    profile_id: uuid.UUID,
    *,
    approved_by_user_id: uuid.UUID,
    approval_basis: str,
) -> RequirementProfile:
    """Утвердить черновик. Прежняя утверждённая версия той же должности **в том же контуре**
    уходит в архив: утверждение учебного профиля не трогает рабочий, и наоборот.

    Утверждает активный пользователь с ролью hr или admin; основание обязательно —
    одинаково для рабочего и учебного профиля, чтобы проверка учебного шла тем же путём.
    """
    profile = _get(session, RequirementProfile, profile_id, "профиль требований")
    user = _get(session, User, approved_by_user_id, "пользователь")
    if profile.status != RequirementStatus.DRAFT:
        raise RepositoryError(f"утвердить можно только черновик, а профиль в статусе «{profile.status.value}»")
    if not user.is_active or user.role not in (UserRole.HR, UserRole.ADMIN):
        raise RepositoryError("утверждает активный кадровик или администратор")
    if not approval_basis.strip():
        raise RepositoryError("не указано основание утверждения")

    # Сначала архив, затем утверждение: иначе сработает индекс «одна утверждённая на должность в контуре».
    session.execute(
        update(RequirementProfile)
        .where(
            RequirementProfile.position_id == profile.position_id,
            RequirementProfile.is_synthetic == profile.is_synthetic,
            RequirementProfile.status == RequirementStatus.APPROVED,
        )
        .values(status=RequirementStatus.ARCHIVED)
    )
    session.flush()
    profile.status = RequirementStatus.APPROVED
    profile.approved_by_user_id = user.id
    profile.approved_at = func.now()
    profile.approval_basis = approval_basis.strip()
    session.flush()
    session.refresh(profile)
    return profile


def get_approved_profile(
    session: Session, position_id: uuid.UUID, *, synthetic: bool = False
) -> RequirementProfile | None:
    """Действующий (утверждённый) профиль должности — единственное место такого выбора.

    По умолчанию — рабочий контур: учебный профиль сюда не попадает, даже если он утверждён.
    Учебный выбирается только явным synthetic=True (технический прогон, учебный срез API).
    """
    return session.scalar(
        select(RequirementProfile).where(
            RequirementProfile.position_id == position_id,
            RequirementProfile.is_synthetic == synthetic,
            RequirementProfile.status == RequirementStatus.APPROVED,
        )
    )


# --- Оценка ------------------------------------------------------------------

def is_training_assessment(candidate: Candidate, profile: RequirementProfile) -> bool:
    """Оценка учебная, если учебный кандидат или профиль. Рабочая рекомендация — только
    рабочий кандидат × рабочий профиль (а такой профиль save_assessment пускает только утверждённым)."""
    return candidate.is_synthetic or profile.is_synthetic


def is_preliminary(result: CheckResult, basis: VerificationMethod, verification: VerificationMethod) -> bool:
    """Результат предварительный: вывод есть, но сделан не тем способом, которым требование
    подтверждается (контракт оценки п. 4.4). Пример: «Высшее образование» по резюме при
    verification = documents — «по резюме да, нужен документ»; «среднее» по резюме при том же
    требовании — «по резюме нет, сверить с документом». unknown — не вывод, поэтому не предварительный."""
    return result != CheckResult.UNKNOWN and basis != verification


def _check_assessment_allowed(candidate: Candidate, profile: RequirementProfile) -> None:
    """Кого по какому профилю можно оценивать — правило держит база, а не только оценщик.

    Реальный кандидат — только по утверждённому рабочему профилю: иначе черновик или
    учебное правило («стаж ≥ 24 мес.») превратились бы в рабочую рекомендацию о человеке.
    Учебный кандидат — по любому не архивному профилю: так учебные случаи проверяют и
    правила реальных профилей.
    """
    if profile.status == RequirementStatus.ARCHIVED:
        raise RepositoryError("профиль в архиве: оценивать нужно по действующей версии требований")
    if candidate.is_synthetic:
        return
    if profile.is_synthetic:
        raise RepositoryError("реального кандидата нельзя оценивать по учебному профилю")
    if profile.status != RequirementStatus.APPROVED:
        raise RepositoryError("реального кандидата оценивают только по утверждённому профилю")


def save_assessment(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    profile_id: uuid.UUID,
    card_id: uuid.UUID,
    model: str,
    formal_checks: Sequence[FormalCheckIn],
    competency_scores: Sequence[CompetencyScoreIn],
    overall_score: int | None = None,
    summary: str | None = None,
    prompt_version: str | None = None,
    algorithm_version: str | None = None,
    calculation_as_of: str | None = None,
) -> Assessment:
    """Сохранить новую версию оценки кандидата по версии требований (вывод модели по резюме).

    Проверяется: кого по какому профилю можно оценивать (контур и статус профиля);
    требования и компетенции из этого же профиля; каждая цитата стоит ровно на указанном
    месте в том очищенном тексте, из которого извлечена карточка; альтернативы — все
    ключи требования, итог строки следует из них. Основание всех строк — resume.
    Итог по формальным требованиям считает код, а не модель.
    """
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    profile = _get(session, RequirementProfile, profile_id, "профиль требований")
    _check_assessment_allowed(candidate, profile)
    card = _get(session, CandidateCard, card_id, "карточка")
    if card.candidate_id != candidate.id:
        raise RepositoryError("карточка принадлежит другому кандидату")

    requirements = _profile_requirements(session, profile.id)
    competency_ids = set(session.scalars(select(Competency.id).where(Competency.profile_id == profile.id)))
    # Одно требование или компетенция — одна строка: иначе в оценке окажутся два
    # противоречивых вывода, а formal_result посчитается только по последнему.
    _reject_repeats([c.requirement_id for c in formal_checks], "требование")
    _reject_repeats([s.competency_id for s in competency_scores], "компетенция")
    for check in formal_checks:
        if check.requirement_id not in requirements:
            raise RepositoryError(f"требование {check.requirement_id} не из профиля {profile.id}")
        _check_alternatives(check, requirements[check.requirement_id])
    for score in competency_scores:
        if score.competency_id not in competency_ids:
            raise RepositoryError(f"компетенция {score.competency_id} не из профиля {profile.id}")
        _validate_competency_details(score, session.get(Competency, score.competency_id))

    all_evidence = [e for item in [*formal_checks, *competency_scores] for e in item.evidence]
    all_evidence += [e for check in formal_checks for alt in check.alternatives for e in alt.evidence]
    all_evidence += [e for score in competency_scores if score.details
                     for indicator in score.details.indicators for e in indicator.evidence]
    _verify_evidence(session, candidate.id, card.candidate_text_id, all_evidence)

    rows = [
        FormalCheck(
            requirement_id=check.requirement_id,
            result=check.result,
            basis=VerificationMethod.RESUME,
            explanation=check.explanation,
            evidence=[e.model_dump(mode="json") for e in check.evidence],
            alternatives=[a.model_dump(mode="json") for a in check.alternatives],
        )
        for check in formal_checks
    ]
    scores = [
        CompetencyScore(
            competency_id=score.competency_id,
            level=score.level,
            explanation=score.explanation,
            evidence=[e.model_dump(mode="json") for e in score.evidence],
            details=score.details.model_dump(mode='json') if score.details else None,
        )
        for score in competency_scores
    ]
    return _add_assessment_version(
        session, candidate.id, profile.id, card.id, requirements, rows, scores,
        model=model, prompt_version=prompt_version, algorithm_version=algorithm_version,
        calculation_as_of=calculation_as_of,
        overall_score=overall_score, summary=summary,
    )


def confirm_formal_check(
    session: Session,
    *,
    assessment_id: uuid.UUID,
    requirement_id: uuid.UUID,
    result: CheckResult,
    basis: VerificationMethod,
    actor_user_id: uuid.UUID,
    comment: str,
) -> Assessment:
    """Человек вносит результат требования по документу, интервью или тесту.

    Создаётся новая версия оценки: все строки текущей копируются, строка требования
    заменяется результатом с основанием basis, итог пересчитывается. Прежняя версия
    остаётся в истории (is_current = false): видно, что было «по резюме», а что — «по документу».
    Цитат резюме у такой строки нет; основание описывает comment («диплом проверен»;
    номера и серии документов не пишутся — это ПДн).
    """
    if basis == VerificationMethod.RESUME:
        raise RepositoryError("по резюме результат пишет save_assessment; здесь — документ, интервью или тест")
    if not comment.strip():
        raise RepositoryError("не указано, на каком основании подтверждён результат")
    current = _get(session, Assessment, assessment_id, "оценка")
    if not current.is_current:
        raise RepositoryError("подтверждать можно только текущую версию оценки")
    user = _get(session, User, actor_user_id, "пользователь")
    if not user.is_active or user.role not in (UserRole.HR, UserRole.ADMIN):
        raise RepositoryError("подтверждает активный кадровик или администратор")
    candidate = _get(session, Candidate, current.candidate_id, "кандидат")
    profile = _get(session, RequirementProfile, current.profile_id, "профиль требований")
    _check_assessment_allowed(candidate, profile)
    requirements = _profile_requirements(session, profile.id)
    if requirement_id not in requirements:
        raise RepositoryError(f"требование {requirement_id} не из профиля {profile.id}")

    rows = [
        FormalCheck(
            requirement_id=old.requirement_id,
            result=old.result,
            basis=old.basis,
            explanation=old.explanation,
            evidence=old.evidence,
            alternatives=old.alternatives,
            confirmed_by_user_id=old.confirmed_by_user_id,
        )
        for old in current.formal_checks
        if old.requirement_id != requirement_id
    ]
    rows.append(
        FormalCheck(
            requirement_id=requirement_id,
            result=result,
            basis=basis,
            explanation=comment.strip(),
            evidence=[],
            alternatives=[],
            confirmed_by_user_id=user.id,
        )
    )
    scores = [
        CompetencyScore(
            competency_id=old.competency_id, level=old.level, explanation=old.explanation, evidence=old.evidence,
            details=old.details,
        )
        for old in current.competency_scores
    ]
    return _add_assessment_version(
        session, candidate.id, profile.id, current.card_id, requirements, rows, scores,
        model=current.model, prompt_version=current.prompt_version, algorithm_version=current.algorithm_version,
        calculation_as_of=current.calculation_as_of,
        overall_score=current.overall_score, summary=current.summary,
    )


def _profile_requirements(session: Session, profile_id: uuid.UUID) -> dict[uuid.UUID, FormalRequirement]:
    return {r.id: r for r in session.scalars(select(FormalRequirement).where(FormalRequirement.profile_id == profile_id))}


def _add_assessment_version(
    session: Session,
    candidate_id: uuid.UUID,
    profile_id: uuid.UUID,
    card_id: uuid.UUID,
    requirements: dict[uuid.UUID, FormalRequirement],
    rows: list[FormalCheck],
    scores: list[CompetencyScore],
    **fields: Any,
) -> Assessment:
    """Новая текущая версия оценки в паре (кандидат, профиль); итог по формальным и
    признаки предварительности считает код."""
    for row in rows:
        row.is_preliminary = is_preliminary(row.result, row.basis, requirements[row.requirement_id].verification)
    formal = _formal_result({r.requirement_id: r.result for r in rows}, requirements)
    version = _next_version(
        session, Assessment.version, Assessment.candidate_id == candidate_id, Assessment.profile_id == profile_id
    )
    _clear_current(session, Assessment, Assessment.candidate_id == candidate_id, Assessment.profile_id == profile_id)
    assessment = Assessment(
        candidate_id=candidate_id,
        profile_id=profile_id,
        card_id=card_id,
        version=version,
        is_current=True,
        formal_result=formal,
        formal_preliminary=formal == CheckResult.MET and any(
            r.is_preliminary for r in rows if _in_gate(requirements[r.requirement_id])
        ),
        **fields,
    )
    assessment.formal_checks = rows
    assessment.competency_scores = scores
    session.add(assessment)
    session.flush()
    return assessment


def _validate_competency_details(score, competency) -> None:
    from app.assessment.counters import aggregate_competency, validate_groups
    if score.details is None:
        return  # legacy scores remain readable by existing callers
    try:
        validate_groups([competency])
    except ValueError as error:
        raise RepositoryError(str(error)) from error
    results = score.details.indicators
    keys = [r.key for r in results]
    expected = {i.key for i in competency.indicators
                if i.check_stage == 'screening' and not i.excluded_from_scoring}
    if set(keys) != expected or len(keys) != len(expected):
        raise RepositoryError('details must contain every screening indicator exactly once')
    if any(r.status != 'no_info' and not r.evidence for r in results):
        raise RepositoryError('confirmed/contradicted indicator requires evidence')
    calculated = aggregate_competency(competency.indicators, {r.key: r.status for r in results})
    calculated.indicators = results
    if calculated != score.details:
        raise RepositoryError('competency counters or groups contradict indicator results')


def _reject_repeats(ids: Sequence[uuid.UUID], label: str) -> None:
    repeated = sorted({str(i) for i in ids if ids.count(i) > 1})
    if repeated:
        raise RepositoryError(f"{label} оценено в одной оценке дважды: {', '.join(repeated)}")


def _check_alternatives(check: FormalCheckIn, requirement: FormalRequirement) -> None:
    """Результаты альтернатив: либо не переданы, либо переданы все ключи требования ровно
    по разу, и итог строки им не противоречит (met — хоть одна met; not_met — все not_met;
    иначе unknown, который допустим всегда). Так в базе не окажется «требование выполнено»
    при всех опровергнутых путях."""
    if not check.alternatives:
        return
    expected = alternative_keys(requirement.params)
    given = [a.key for a in check.alternatives]
    if not expected:
        raise RepositoryError(f"у требования {requirement.key} нет альтернатив, а результаты альтернатив переданы")
    if sorted(given) != sorted(expected):
        raise RepositoryError(
            f"альтернативы требования {requirement.key}: нужны ровно {', '.join(expected)}, переданы {', '.join(given)}"
        )
    # unknown допустим всегда: направление проверяется только при подтверждённом уровне
    # (requires_requirement), поэтому при подтверждённой альтернативе итог бывает unknown.
    # Противоречием считаются только «выполнено» без выполненной альтернативы и
    # «не выполнено», пока хоть одна альтернатива не опровергнута.
    combined = combine_alternatives(check.alternatives)
    if check.result != CheckResult.UNKNOWN and check.result != combined:
        raise RepositoryError(
            f"итог требования {requirement.key} = {check.result.value}, а по альтернативам выходит {combined.value}"
        )


def combine_alternatives(alternatives: Sequence[AlternativeResultIn]) -> CheckResult:
    """Правило альтернатив (контракт оценки п. 4.2): OR между альтернативами."""
    results = [a.result for a in alternatives]
    if CheckResult.MET in results:
        return CheckResult.MET
    if results and all(r == CheckResult.NOT_MET for r in results):
        return CheckResult.NOT_MET
    return CheckResult.UNKNOWN


def _in_gate(requirement: FormalRequirement) -> bool:
    """Требование входит в итог разбора резюме: обязательное и этапа screening."""
    return requirement.is_mandatory and requirement.check_stage == CheckStage.SCREENING


def _formal_result(
    results: dict[uuid.UUID, CheckResult], requirements: dict[uuid.UUID, FormalRequirement]
) -> CheckResult:
    """Итог разбора резюме по обязательным требованиям этапа screening: хоть одно
    не выполнено → not_met; хоть одно без сведений или не проверено → unknown; иначе met.
    Требования этапа interview в итог не входят. Предварительный met (по резюме при
    verification = documents) считается met: на первичном отборе это и есть вывод по резюме,
    а пометку «нужен документ» показывает is_preliminary."""
    gate = [r.id for r in requirements.values() if _in_gate(r)]
    if any(results.get(r) == CheckResult.NOT_MET for r in gate):
        return CheckResult.NOT_MET
    if any(results.get(r, CheckResult.UNKNOWN) == CheckResult.UNKNOWN for r in gate):
        return CheckResult.UNKNOWN
    return CheckResult.MET


def _verify_evidence(
    session: Session, candidate_id: uuid.UUID, card_text_id: uuid.UUID, evidence: Sequence[Evidence]
) -> None:
    """Цитата стоит на месте в тексте этого кандидата, из которого извлечена карточка оценки."""
    text_ids = {e.candidate_text_id for e in evidence}
    texts = {
        t.id: t for t in session.scalars(select(CandidateText).where(CandidateText.id.in_(text_ids)))
    } if text_ids else {}
    for item in evidence:
        text_row = texts.get(item.candidate_text_id)
        if text_row is None or text_row.candidate_id != candidate_id:
            raise EvidenceError(f"цитата ссылается на чужой или несуществующий текст: «{item.quote[:60]}»")
        if item.candidate_text_id != card_text_id:
            raise EvidenceError(f"цитата не из того текста, по которому извлечена карточка: «{item.quote[:60]}»")
        if not evidence_matches(text_row.text, item):
            raise EvidenceError(f"цитаты нет в тексте резюме на указанном месте: «{item.quote[:60]}»")


# --- Версии ------------------------------------------------------------------

def _next_version(session: Session, version_column, *conditions) -> int:
    current_max = session.scalar(select(func.max(version_column)).where(*conditions))
    return (current_max or 0) + 1


def _clear_current(session: Session, model, *conditions) -> None:
    """Снять отметку «текущая» со старой версии до вставки новой —
    иначе сработает уникальный индекс «одна текущая версия»."""
    session.execute(update(model).where(*conditions, model.is_current).values(is_current=False))
    session.flush()
