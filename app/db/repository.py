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
from datetime import date
from pathlib import PurePath
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.db.enums import (
    ApplicationSource,
    AuditAction,
    Channel,
    CheckResult,
    DocumentKind,
    FeedbackOutcome,
    FileFormat,
    ReserveStatus,
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
    CompetencyScore,
    DepartmentFeedback,
    FormalCheck,
    FormalRequirement,
    RejectionReason,
    RequirementProfile,
    ReserveEntry,
    SelectionStage,
    SourceDocument,
    StageEvent,
    Vacancy,
)
from app.db.seed import INITIAL_STAGE
from app.schemas.assessment import CompetencyScoreIn, FormalCheckIn
from app.schemas.card import CandidateCard as CardSchema
from app.schemas.card import Evidence, evidence_matches
from app.schemas.pii import PiiData


class RepositoryError(Exception):
    """Нарушено правило работы с данными."""


class StageTransitionError(RepositoryError):
    pass


class EvidenceError(RepositoryError):
    pass


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
) -> Candidate:
    """Создать кандидата из резюме: запись кандидата, его ПДн и первую версию очищенного текста."""
    source_document = _get(session, SourceDocument, source_document_id, "исходный документ")
    if source_document.kind != DocumentKind.RESUME:
        raise RepositoryError(f"документ {source_document.original_path} не резюме: {source_document.kind}")

    candidate = Candidate(code=code, source_document_id=source_document.id, headline=headline)
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
) -> StageEvent:
    """Перевести отклик на другой этап. Меняет текущий этап и пишет событие в журнал одним шагом.

    Правила: из финального этапа (принят, отказ, кандидат отказался) переходов нет;
    причина отказа указывается только при переходе в «Отказ» или «Кандидат отказался».
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
    if rejection_reason_code is not None:
        if target.code not in ("rejected", "withdrawn"):
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
    feedback = DepartmentFeedback(
        application_id=application.id,
        interview_held=interview_held,
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


# --- Кадровый резерв ---------------------------------------------------------

def add_to_reserve(
    session: Session,
    *,
    candidate_id: uuid.UUID,
    position_id: uuid.UUID | None = None,
    competency_area: str | None = None,
    source_application_id: uuid.UUID | None = None,
    reason: str | None = None,
    added_by_user_id: uuid.UUID | None = None,
    valid_until: date | None = None,
) -> ReserveEntry:
    """Добавить кандидата в резерв. Если он уже в активном резерве на ту же должность
    или направление — вернуть существующую запись, а не создавать дубль."""
    if position_id is None and not competency_area:
        raise RepositoryError("резерв нужен на должность или на направление")
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    if source_application_id is not None:
        _get(session, Application, source_application_id, "отклик")
    existing = session.scalar(
        select(ReserveEntry).where(
            ReserveEntry.candidate_id == candidate.id,
            ReserveEntry.status == ReserveStatus.ACTIVE,
            ReserveEntry.position_id.is_(None) if position_id is None else ReserveEntry.position_id == position_id,
            ReserveEntry.competency_area.is_(None)
            if competency_area is None
            else ReserveEntry.competency_area == competency_area,
        )
    )
    if existing is not None:
        return existing
    entry = ReserveEntry(
        candidate_id=candidate.id,
        position_id=position_id,
        competency_area=competency_area,
        source_application_id=source_application_id,
        reason=reason,
        added_by_user_id=added_by_user_id,
        valid_until=valid_until,
    )
    session.add(entry)
    session.flush()
    return entry


def reserve_for_position(session: Session, position_id: uuid.UUID, *, today: date | None = None) -> list[ReserveEntry]:
    """Активный резерв на должность с неистёкшим сроком. Резерв «по направлению»
    сюда не входит: его подбирает поиск по смыслу."""
    today = today or date.today()
    return list(
        session.scalars(
            select(ReserveEntry)
            .where(
                ReserveEntry.position_id == position_id,
                ReserveEntry.status == ReserveStatus.ACTIVE,
                or_(ReserveEntry.valid_until.is_(None), ReserveEntry.valid_until >= today),
            )
            .order_by(ReserveEntry.added_at)
        )
    )


# --- Оценка ------------------------------------------------------------------

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
) -> Assessment:
    """Сохранить новую версию оценки кандидата по версии требований.

    Проверяется: требования и компетенции из этого же профиля; каждая цитата стоит
    в очищенном тексте этого кандидата ровно на указанном месте. Итог по формальным
    требованиям считает код, а не модель: не выполнено обязательное → not_met.
    """
    candidate = _get(session, Candidate, candidate_id, "кандидат")
    profile = _get(session, RequirementProfile, profile_id, "профиль требований")
    card = _get(session, CandidateCard, card_id, "карточка")
    if card.candidate_id != candidate.id:
        raise RepositoryError("карточка принадлежит другому кандидату")

    requirements = {
        r.id: r for r in session.scalars(select(FormalRequirement).where(FormalRequirement.profile_id == profile.id))
    }
    competency_ids = set(session.scalars(select(Competency.id).where(Competency.profile_id == profile.id)))
    for check in formal_checks:
        if check.requirement_id not in requirements:
            raise RepositoryError(f"требование {check.requirement_id} не из профиля {profile.id}")
    for score in competency_scores:
        if score.competency_id not in competency_ids:
            raise RepositoryError(f"компетенция {score.competency_id} не из профиля {profile.id}")

    all_evidence = [e for item in [*formal_checks, *competency_scores] for e in item.evidence]
    _verify_evidence(session, candidate.id, all_evidence)

    version = _next_version(
        session,
        Assessment.version,
        Assessment.candidate_id == candidate.id,
        Assessment.profile_id == profile.id,
    )
    _clear_current(session, Assessment, Assessment.candidate_id == candidate.id, Assessment.profile_id == profile.id)

    assessment = Assessment(
        candidate_id=candidate.id,
        profile_id=profile.id,
        card_id=card.id,
        version=version,
        is_current=True,
        model=model,
        prompt_version=prompt_version,
        formal_result=_formal_result(formal_checks, requirements),
        overall_score=overall_score,
        summary=summary,
    )
    session.add(assessment)
    session.flush()
    for check in formal_checks:
        session.add(
            FormalCheck(
                assessment_id=assessment.id,
                requirement_id=check.requirement_id,
                result=check.result,
                explanation=check.explanation,
                evidence=[e.model_dump(mode="json") for e in check.evidence],
            )
        )
    for score in competency_scores:
        session.add(
            CompetencyScore(
                assessment_id=assessment.id,
                competency_id=score.competency_id,
                level=score.level,
                explanation=score.explanation,
                evidence=[e.model_dump(mode="json") for e in score.evidence],
            )
        )
    session.flush()
    return assessment


def _formal_result(
    checks: Sequence[FormalCheckIn], requirements: dict[uuid.UUID, FormalRequirement]
) -> CheckResult:
    """Итог по обязательным требованиям: хоть одно не выполнено → not_met;
    хоть одно без сведений или не проверено → unknown; иначе met."""
    results = {c.requirement_id: c.result for c in checks}
    mandatory = [r.id for r in requirements.values() if r.is_mandatory]
    if any(results.get(r) == CheckResult.NOT_MET for r in mandatory):
        return CheckResult.NOT_MET
    if any(results.get(r, CheckResult.UNKNOWN) == CheckResult.UNKNOWN for r in mandatory):
        return CheckResult.UNKNOWN
    return CheckResult.MET


def _verify_evidence(session: Session, candidate_id: uuid.UUID, evidence: Sequence[Evidence]) -> None:
    text_ids = {e.candidate_text_id for e in evidence}
    texts = {
        t.id: t for t in session.scalars(select(CandidateText).where(CandidateText.id.in_(text_ids)))
    } if text_ids else {}
    for item in evidence:
        text_row = texts.get(item.candidate_text_id)
        if text_row is None or text_row.candidate_id != candidate_id:
            raise EvidenceError(f"цитата ссылается на чужой или несуществующий текст: «{item.quote[:60]}»")
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
