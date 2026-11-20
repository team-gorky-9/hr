"""Передача отклика получателю, очищенная сводка, очередь ожиданий и ответы департамента (workflow-01).

Сводка (GET /handoff-summary) ничего не пишет в базу и не создаёт ожиданий.
Подтверждение передачи (POST /stage → sent_to_department) в одной транзакции меняет
этап и записывает попытку с замороженным снимком сводки.

Доступ к CandidatePii внутри этого модуля используется исключительно для фильтрации
заметок кадровика и интервью (Р8-A1): заметки с контактами или ПДн кандидата
исключаются целиком и никогда не попадают в DTO и Markdown.
"""
import hashlib
import importlib
import json
import re
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api import services, workflow
from app.api.errors import ApiError, not_found
from app.api.schemas import (
    AssessmentStatus,
    Contour,
    HandoffAttemptDetailOut,
    HandoffAttemptOut,
    HandoffCreateIn,
    HandoffCreatedOut,
    HandoffFeedbackCreatedOut,
    HandoffFeedbackIn,
    HandoffFeedbackListOut,
    HandoffFeedbackOut,
    HandoffIn,
    HandoffListOut,
    HandoffSummaryInterviewItemOut,
    HandoffSummaryNoteOut,
    HandoffSummaryOut,
    HandoffSummaryPayloadOut,
    HandoffSummaryQuestionOut,
    OpenWaitsByDepartmentOut,
    OpenWaitsOut,
    StageMoveIn,
    StageMoveOut,
    UserBriefOut,
)
from app.db import repository as repo
from app.db.enums import (
    ApplicationSource,
    CheckResult,
    CheckStage,
    FeedbackOutcome,
    HandoffChannel,
    HandoffStatus,
    ProcessFactStatus,
    UserRole,
)
from app.db.models import (
    Application,
    Candidate,
    CandidatePii,
    DepartmentFeedback,
    HandoffAttempt,
    Interview,
    Position,
    RejectionReason,
    SelectionStage,
    StageEvent,
    User,
    Vacancy,
)
redact_mod = importlib.import_module("app.ingest.redact")

_URL_ADDRESS_RE = re.compile(r"@|https?://|www\.|[a-z0-9-]\.[a-z]{2,}|\d{5,}", re.IGNORECASE)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _candidate_pii_values(session: Session, candidate_id: uuid.UUID) -> tuple[list[str], list[str]]:
    """Значения ПДн кандидата (длинные строки и короткие 4-символьные слова ФИО) для фильтрации заметок."""
    pii = session.get(CandidatePii, candidate_id)
    if pii is None:
        return [], []
    long_values: list[str] = []
    short_words: list[str] = []
    for item in [
        pii.full_name,
        pii.phone,
        pii.email,
        *(pii.links or []),
        pii.birth_date.isoformat() if pii.birth_date else None,
        pii.birth_date.strftime("%d.%m.%Y") if pii.birth_date else None,
    ]:
        if item and len(item.strip()) >= 5:
            long_values.append(item.strip())
    if pii.full_name:
        for part in pii.full_name.split():
            cleaned = part.strip()
            if len(cleaned) >= 5:
                long_values.append(cleaned)
            elif len(cleaned) == 4:
                short_words.append(cleaned)
    return long_values, short_words


def contains_pii_or_contact(
    text: str,
    own_pii: tuple[Sequence[str], Sequence[str]] | Sequence[str] = (),
) -> bool:
    """Проверить, есть ли в заметке контакты, ссылки, шаблонные метки или ПДн кандидата."""
    if not text or not text.strip():
        return False
    patterns = (
        redact_mod.EMAIL,
        redact_mod.PHONE,
        redact_mod.PHONE_INTL,
        redact_mod.LONG_DIGITS,
        redact_mod.PROFILE_URL,
        redact_mod.NICK,
        redact_mod.LABELED_PHONE,
        redact_mod.ARCHIVE_NAME,
        redact_mod.ARCHIVE_NUMBER,
        redact_mod.BIRTH_DATE_RESIDUE,
    )
    if any(pattern.search(text) for pattern in patterns):
        return True
    for match in redact_mod.ANY_URL.finditer(text):
        host = match.group("host").lower()
        tld = match.group("tld").lower()
        is_personal = any(host == p or host.endswith(f".{p}") for p in redact_mod.PERSONAL_HOSTS)
        if is_personal or ((match.group("scheme") or match.group("path")) and tld in redact_mod.URL_TLDS):
            return True
    for match in redact_mod.LABELED_FIELD.finditer(text):
        label = match.group("label").casefold()
        value = match.group("value").strip()
        if not value:
            continue
        if re.fullmatch(redact_mod.LINK_LABELS, label) and not _URL_ADDRESS_RE.search(value):
            continue
        return True
    if isinstance(own_pii, tuple) and len(own_pii) == 2 and not isinstance(own_pii[0], str):
        long_values, short_words = own_pii
    else:
        long_values, short_words = own_pii, ()
    lowered = text.casefold()
    if any(value.casefold() in lowered for value in long_values):
        return True
    return any(re.search(rf"(?i)(?<!\w){re.escape(word)}(?!\w)", text) for word in short_words)


def _collect_hr_notes(
    session: Session,
    application_id: uuid.UUID,
    stages: dict[str, SelectionStage],
    own_pii: tuple[Sequence[str], Sequence[str]] | Sequence[str],
) -> tuple[list[HandoffSummaryNoteOut], int]:
    events = repo.stage_history(session, application_id)
    users = workflow._users(session, (e.actor_user_id for e in events))
    notes: list[HandoffSummaryNoteOut] = []
    omitted = 0
    for event in events:
        text = _clean(event.comment)
        if not text:
            continue
        if contains_pii_or_contact(text, own_pii):
            omitted += 1
            continue
        stage = stages[event.to_stage_code]
        notes.append(
            HandoffSummaryNoteOut(
                seq=event.seq,
                stage_code=stage.code,
                stage_title=stage.title,
                actor=workflow.user_out(users.get(event.actor_user_id)),
                created_at=event.created_at,
                text=text,
            )
        )
    return notes, omitted


def _collect_interview_notes(
    session: Session,
    application_id: uuid.UUID,
    own_pii: tuple[Sequence[str], Sequence[str]] | Sequence[str],
) -> tuple[list[HandoffSummaryInterviewItemOut], int]:
    interviews = list(
        session.scalars(
            select(Interview)
            .where(Interview.application_id == application_id)
            .options(selectinload(Interview.questions))
            .order_by(Interview.created_at, Interview.id)
        )
    )
    items: list[HandoffSummaryInterviewItemOut] = []
    omitted = 0
    for interview in interviews:
        summary_text = _clean(interview.summary)
        if summary_text and contains_pii_or_contact(summary_text, own_pii):
            omitted += 1
            summary_text = None
        questions: list[HandoffSummaryQuestionOut] = []
        for q in interview.questions:
            answer_text = _clean(q.answer_notes)
            if answer_text and contains_pii_or_contact(answer_text, own_pii):
                omitted += 1
                answer_text = None
            questions.append(
                HandoffSummaryQuestionOut(
                    question_id=q.id,
                    gap=q.gap,
                    question=q.question,
                    answer_text=answer_text,
                )
            )
        items.append(
            HandoffSummaryInterviewItemOut(
                interview_id=interview.id,
                kind=str(interview.kind),
                result=str(interview.result),
                held_at=interview.held_at,
                summary=summary_text,
                questions=questions,
            )
        )
    return items, omitted


def _collect_referenced_text_ids(detail) -> list[str]:
    ids: set[str] = set()
    if detail.candidate.current_text_id is not None:
        ids.add(str(detail.candidate.current_text_id))
    assessment = detail.assessment
    if assessment is not None:
        for check in assessment.formal_checks:
            for ev in check.evidence:
                ids.add(str(ev.candidate_text_id))
            for alt in check.alternatives:
                for ev in alt.evidence:
                    ids.add(str(ev.candidate_text_id))
        for score in assessment.competency_scores:
            for ev in score.evidence:
                ids.add(str(ev.candidate_text_id))
            if score.details is not None:
                for indicator in score.details.indicators:
                    for ev in indicator.evidence:
                        ids.add(str(ev.candidate_text_id))
    return sorted(ids)


def _render_markdown(payload: HandoffSummaryPayloadOut) -> str:
    lines: list[str] = [f"# Сводка по кандидату {payload.candidate_code}"]
    if payload.vacancy is not None:
        lines.append(f"**Вакансия:** {payload.vacancy.title} ({payload.vacancy.position_code})")
    if payload.posting_title:
        lines.append(f"**Публикация:** {payload.posting_title}")
    lines.append(f"**Текущий этап:** {payload.stage.title} (`{payload.stage.code}`)")
    if payload.warnings:
        lines.append("")
        lines.append("## Предупреждения")
        for warning in payload.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append("## Карточка (без ПДн)")
    headline = payload.candidate_brief.get("headline")
    if headline:
        lines.append(f"- Профиль: {headline}")
    exp_years = payload.candidate_brief.get("experience_years")
    if exp_years is not None:
        lines.append(f"- Заявленный стаж: {exp_years} г.")
    skills = payload.candidate_brief.get("skills") or []
    if skills:
        names = ", ".join(s.get("name", "") for s in skills if isinstance(s, dict) and s.get("name"))
        if names:
            lines.append(f"- Навыки: {names}")

    lines.append("")
    lines.append("## Оценка")
    lines.append(f"- Статус оценки: `{payload.assessment_status}`")
    if payload.formal_summary is not None:
        prelim = " (предварительно)" if payload.formal_summary.get("formal_preliminary") else ""
        lines.append(f"- Формальный итог: `{payload.formal_summary.get('formal_result')}`{prelim}")
        if payload.formal_summary.get("overall_score") is not None:
            lines.append(f"- Балл по компетенциям: {payload.formal_summary.get('overall_score')}")
        for check in payload.formal_summary.get("formal_checks", []):
            lines.append(
                f"  - {check.get('description')}: `{check.get('result')}` "
                f"(основание: `{check.get('basis')}`, этап: `{check.get('check_stage')}`)"
            )
    if payload.competencies:
        lines.append("- Компетенции и цитаты:")
        for comp in payload.competencies:
            level_txt = f" — уровень {comp['level']}" if comp.get("level") is not None else ""
            lines.append(f"  - **{comp.get('name')}** (`{comp.get('code')}`){level_txt}")
            for ev in comp.get("evidence", []):
                lines.append(f"    - «{ev.get('quote')}» (`{ev.get('candidate_text_id')}`)")

    lines.append("")
    lines.append("## Пробелы и вопросы")
    for label, key in (
        ("Не хватает в резюме", "card_missing"),
        ("Не подтверждено на первичном отборе", "screening_unknown"),
        ("Вопросы для этапа интервью", "interview_requirements"),
    ):
        items = payload.gaps.get(key) or []
        if items:
            lines.append(f"- {label}: " + "; ".join(items))

    if payload.interview_notes:
        lines.append("")
        lines.append("## Итоги интервью")
        for item in payload.interview_notes:
            lines.append(f"- Интервью `{item.kind}` ({item.result})")
            if item.summary:
                lines.append(f"  - Резюме встречи: {item.summary}")
            for q in item.questions:
                ans = q.answer_text if q.answer_text is not None else "—"
                lines.append(f"  - Вопрос: {q.question} → Ответ: {ans}")

    if payload.hr_notes:
        lines.append("")
        lines.append("## Заметки кадровика")
        for note in payload.hr_notes:
            actor = note.actor.login if note.actor else "система"
            lines.append(f"- [{note.stage_title}, {actor}] {note.text}")

    return "\n".join(lines)


def build_handoff_summary(session: Session, application_id: uuid.UUID) -> HandoffSummaryOut:
    """Собрать предпросмотр сводки для руководителя без ПДн и без записи в БД."""
    application = workflow.get_application_or_404(session, application_id)
    workflow.require_working_application(application)
    detail = services.get_application(session, application_id)
    stages = workflow._stages(session)
    own_pii = _candidate_pii_values(session, detail.candidate.candidate_id)

    hr_notes, omitted_hr = _collect_hr_notes(session, application_id, stages, own_pii)
    interview_notes, omitted_interview = _collect_interview_notes(session, application_id, own_pii)
    omitted_total = omitted_hr + omitted_interview

    card = detail.candidate.card or {}
    candidate_brief = {
        "headline": detail.candidate.headline,
        "experience_years": card.get("experience_years"),
        "education": card.get("education", []),
        "courses": card.get("courses", []),
        "experience": card.get("experience", []),
        "skills": card.get("skills", []),
        "languages": card.get("languages", []),
        "about": card.get("about"),
        "cover_letter": card.get("cover_letter"),
        "missing": card.get("missing", []),
    }

    assessment = detail.assessment
    card_version = card.get("version")
    versions = {
        "candidate_text_id": str(detail.candidate.current_text_id) if detail.candidate.current_text_id else None,
        "card_version": card_version,
        "assessment_id": str(assessment.assessment_id) if assessment else None,
        "assessment_version": assessment.version if assessment else None,
        "profile_id": str(assessment.profile_id) if assessment else None,
        "profile_version": assessment.profile_version if assessment else None,
        "profile_status": str(assessment.profile_status) if assessment else None,
    }

    formal_summary = None
    competencies: list[dict[str, Any]] = []
    screening_unknown: list[str] = []
    interview_reqs: list[str] = []
    stale_reason = assessment.stale_reason if assessment else None

    if assessment is not None:
        formal_summary = {
            "formal_result": str(assessment.formal_result),
            "formal_preliminary": assessment.formal_preliminary,
            "overall_score": assessment.overall_score,
            "summary": assessment.summary,
            "formal_checks": [c.model_dump(mode="json") for c in assessment.formal_checks],
        }
        competencies = [c.model_dump(mode="json") for c in assessment.competency_scores]
        screening_unknown = [
            c.description
            for c in assessment.formal_checks
            if c.check_stage == CheckStage.SCREENING and c.result == CheckResult.UNKNOWN
        ]
        interview_reqs = [
            c.description
            for c in assessment.formal_checks
            if c.check_stage == CheckStage.INTERVIEW
        ]

    warnings: list[str] = []
    if detail.candidate.is_training:
        warnings.append("Учебный пример — не рабочая рекомендация")
    if detail.assessment_status == AssessmentStatus.STALE:
        warnings.append(f"Оценка устарела ({stale_reason or 'stale'})")
    elif detail.assessment_status in (
        AssessmentStatus.NOT_ASSESSED,
        AssessmentStatus.NO_APPROVED_PROFILE,
        AssessmentStatus.NOT_APPLICABLE,
        AssessmentStatus.MAPPING_REQUIRED,
    ):
        warnings.append(f"Актуальная оценка отсутствует ({detail.assessment_status})")
    if omitted_total:
        warnings.append(f"Исключены заметки с подозрением на контакты или ПДн: {omitted_total}")

    payload = HandoffSummaryPayloadOut(
        application_id=detail.application_id,
        candidate_id=detail.candidate.candidate_id,
        candidate_code=detail.candidate.code,
        is_training=detail.candidate.is_training,
        vacancy=detail.vacancy,
        posting_title=detail.posting_title,
        stage=detail.stage,
        versions=versions,
        assessment_status=detail.assessment_status,
        stale_reason=stale_reason,
        candidate_brief=candidate_brief,
        formal_summary=formal_summary,
        competencies=competencies,
        gaps={
            "card_missing": list(card.get("missing") or []),
            "screening_unknown": screening_unknown,
            "interview_requirements": interview_reqs,
        },
        interview_notes=interview_notes,
        hr_notes=hr_notes,
        omitted_notes_count=omitted_total,
        referenced_text_ids=_collect_referenced_text_ids(detail),
        warnings=warnings,
    )
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    summary_revision = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return HandoffSummaryOut(
        summary_revision=summary_revision,
        summary=payload,
        markdown=_render_markdown(payload),
        from_snapshot=False,
        attempt_id=None,
    )


def get_handoff_summary(session: Session, application_id: uuid.UUID, user: User) -> HandoffSummaryOut:
    """Предпросмотр для HR/admin или замороженная сводка для назначенного получателя департамента."""
    if user.role == UserRole.DEPARTMENT:
        attempt = session.scalar(
            select(HandoffAttempt)
            .where(
                HandoffAttempt.application_id == application_id,
                HandoffAttempt.recipient_user_id == user.id,
            )
            .order_by(HandoffAttempt.handed_off_at.desc(), HandoffAttempt.created_at.desc())
        )
        if attempt is None:
            raise ApiError(
                403,
                "FORBIDDEN_SCOPE",
                "Сводка доступна только назначенному получателю передачи",
                {"application_id": str(application_id)},
            )
        return HandoffSummaryOut(
            summary_revision=attempt.summary_revision,
            summary=HandoffSummaryPayloadOut.model_validate(attempt.summary_snapshot["summary"]),
            markdown=attempt.summary_snapshot["markdown"],
            from_snapshot=True,
            attempt_id=attempt.id,
        )
    return build_handoff_summary(session, application_id)


def _resolve_recipient(session: Session, body: HandoffIn) -> tuple[uuid.UUID | None, str, str]:
    if body.recipient_user_id is not None:
        recipient = session.get(User, body.recipient_user_id)
        if recipient is None:
            raise not_found("RECIPIENT_NOT_FOUND", "Получатель не найден", user_id=body.recipient_user_id)
        if not recipient.is_active or recipient.role != UserRole.DEPARTMENT:
            raise ApiError(
                422,
                "RECIPIENT_INVALID",
                "Получатель передачи должен быть активным сотрудником департамента",
                {"user_id": str(recipient.id)},
            )
        department = _clean(body.recipient_department) or _clean(recipient.department)
        name = _clean(body.recipient_name) or _clean(recipient.full_name)
        if not department or not name:
            raise ApiError(
                422,
                "HANDOFF_RECIPIENT_REQUIRED",
                "Укажите имя получателя и подразделение",
                {},
            )
        return recipient.id, name, department

    name = _clean(body.recipient_name)
    department = _clean(body.recipient_department)
    if not name or not department:
        raise ApiError(
            422,
            "HANDOFF_RECIPIENT_REQUIRED",
            "Укажите recipient_user_id или оба поля: recipient_name и recipient_department",
            {},
        )
    return None, name, department


def _feedback_out(
    fb: DepartmentFeedback,
    reasons: dict[str, RejectionReason],
    users: dict[uuid.UUID, User],
    *,
    is_current: bool,
) -> HandoffFeedbackOut:
    return HandoffFeedbackOut(
        feedback_id=fb.id,
        application_id=fb.application_id,
        attempt_id=fb.attempt_id,
        revision=fb.revision,
        supersedes_id=fb.supersedes_id,
        is_current=is_current,
        origin_unrecorded=fb.attempt_id is None,
        outcome=fb.outcome,
        contact_status=fb.contact_status,
        interview_status=fb.interview_status,
        interview_held=fb.interview_held,
        confirmed_competencies=list(fb.confirmed_competencies or []),
        gaps=fb.gaps,
        rejection_reason=workflow.reason_out(reasons.get(fb.rejection_reason_code)) if fb.rejection_reason_code else None,
        keep_in_reserve=fb.keep_in_reserve,
        comment=fb.comment,
        response_channel=fb.response_channel,
        reported_by_name=fb.reported_by_name,
        reported_by=workflow.user_out(users.get(fb.reported_by_user_id)),
        reported_at=fb.reported_at,
        recorded_by=workflow.user_out(users.get(fb.author_user_id)),
        received_at=fb.received_at,
    )


def _attempt_out(
    session: Session,
    attempt: HandoffAttempt,
    *,
    as_of: datetime,
    feedback_by_attempt: dict[uuid.UUID, list[DepartmentFeedback]] | None = None,
    reasons: dict[str, RejectionReason] | None = None,
    users: dict[uuid.UUID, User] | None = None,
) -> HandoffAttemptOut:
    application = session.get(Application, attempt.application_id)
    candidate = session.get(Candidate, application.candidate_id)
    vacancy = session.get(Vacancy, application.vacancy_id) if application.vacancy_id else None
    position = session.get(Position, vacancy.position_id) if vacancy else None

    if feedback_by_attempt is None:
        rows = list(
            session.scalars(
                select(DepartmentFeedback)
                .where(DepartmentFeedback.attempt_id == attempt.id)
                .order_by(DepartmentFeedback.revision)
            )
        )
    else:
        rows = feedback_by_attempt.get(attempt.id, [])
    reasons = reasons if reasons is not None else workflow._reasons(session)
    if users is None:
        uid_set = {attempt.recipient_user_id, attempt.created_by_user_id}
        for row in rows:
            uid_set.update([row.reported_by_user_id, row.author_user_id])
        users = workflow._users(session, uid_set)

    latest_fb = (
        _feedback_out(rows[-1], reasons, users, is_current=True)
        if rows
        else None
    )
    end_dt = _utc(attempt.closed_at) if attempt.closed_at is not None else _utc(as_of)
    wait_hours = max(0.0, round((end_dt - _utc(attempt.handed_off_at)).total_seconds() / 3600.0, 2))
    return HandoffAttemptOut(
        attempt_id=attempt.id,
        application_id=attempt.application_id,
        candidate_id=candidate.id,
        candidate_code=candidate.code,
        is_training=candidate.is_synthetic,
        vacancy_id=vacancy.id if vacancy else None,
        vacancy_title=vacancy.title if vacancy else None,
        position_code=position.code if position else None,
        stage_event_id=attempt.stage_event_id,
        recipient_user=workflow.user_out(users.get(attempt.recipient_user_id)),
        recipient_name=attempt.recipient_name,
        recipient_department=attempt.recipient_department,
        channel=attempt.channel,
        handed_off_at=attempt.handed_off_at,
        created_by=workflow.user_out(users.get(attempt.created_by_user_id)),
        created_at=attempt.created_at,
        summary_revision=attempt.summary_revision,
        status=attempt.status,
        closed_at=attempt.closed_at,
        close_reason=attempt.close_reason,
        wait_hours=wait_hours,
        latest_feedback=latest_fb,
    )


def _validate_and_prepare_handoff(
    session: Session,
    application: Application,
    handoff_in: HandoffIn,
) -> tuple[uuid.UUID | None, str, str, datetime, HandoffSummaryOut]:
    recipient_user_id, recipient_name, recipient_department = _resolve_recipient(session, handoff_in)
    handed_off_at = _utc(handoff_in.handed_off_at) if handoff_in.handed_off_at else datetime.now(timezone.utc)
    summary = build_handoff_summary(session, application.id)
    if summary.summary.assessment_status == AssessmentStatus.STALE and not handoff_in.allow_stale:
        raise ApiError(
            409,
            "ASSESSMENT_STALE",
            "Оценка устарела: пересчитайте оценку или явно подтвердите передачу (allow_stale=true)",
            {"stale_reason": str(summary.summary.stale_reason)},
        )
    if summary.summary_revision != handoff_in.summary_revision:
        raise ApiError(
            409,
            "SUMMARY_CHANGED",
            "Сводка изменилась после предпросмотра: обновите предпросмотр перед отправкой",
            {
                "expected_revision": handoff_in.summary_revision,
                "current_revision": summary.summary_revision,
            },
        )
    return recipient_user_id, recipient_name, recipient_department, handed_off_at, summary


def move_to_sent_with_handoff(
    session: Session,
    application: Application,
    body: StageMoveIn,
    user: User,
) -> tuple[StageMoveOut, bool]:
    """В одной транзакции перевести отклик в sent_to_department и сохранить попытку передачи."""
    assert body.handoff is not None
    handoff_in = body.handoff
    recipient_user_id, recipient_name, recipient_department = _resolve_recipient(session, handoff_in)

    session.refresh(application, with_for_update=True)
    existing_attempt = session.scalar(
        select(HandoffAttempt).where(HandoffAttempt.request_id == handoff_in.request_id)
    )
    if existing_attempt is not None:
        if existing_attempt.stage_event_id is not None and repo._handoff_matches(
            existing_attempt,
            application_id=application.id,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            recipient_department=recipient_department,
            channel=handoff_in.channel,
            summary_revision=handoff_in.summary_revision,
        ):
            stages = workflow._stages(session)
            reasons = workflow._reasons(session)
            event = session.get(StageEvent, existing_attempt.stage_event_id)
            users = workflow._users(session, [event.actor_user_id])
            return (
                StageMoveOut(
                    application_id=application.id,
                    stage=workflow.stage_out(stages[application.current_stage_code]),
                    event=workflow._event_out(event, stages, reasons, users),
                    handoff=_attempt_out(session, existing_attempt, as_of=datetime.now(timezone.utc)),
                ),
                False,
            )
        raise ApiError(409, "REQUEST_ID_REUSED", "request_id уже использован для другой передачи", {})

    current_seq = workflow.last_seq(session, application.id)
    if current_seq != body.expected_seq:
        raise ApiError(
            409,
            "STALE_STAGE_FORM",
            "Отклик уже изменён в другом окне: обновите карточку",
            {
                "expected_seq": body.expected_seq,
                "last_seq": current_seq,
                "current_stage_code": application.current_stage_code,
            },
        )

    recipient_user_id, recipient_name, recipient_department, handed_off_at, summary = _validate_and_prepare_handoff(
        session, application, handoff_in
    )
    snapshot = {
        "summary": summary.summary.model_dump(mode="json"),
        "markdown": summary.markdown,
        "referenced_text_ids": summary.summary.referenced_text_ids,
    }
    current_code = application.current_stage_code
    with session.begin_nested():
        try:
            event = repo.move_application(
                session,
                application.id,
                "sent_to_department",
                actor_user_id=user.id,
                comment=workflow._clean(body.comment),
                rejection_reason_code=body.rejection_reason_code,
                confirm_skip=body.confirm_skip,
            )
        except repo.StageTransitionError as error:
            raise ApiError(
                409,
                "STAGE_TRANSITION_CONFLICT",
                workflow._sentence(str(error)),
                {"current_stage_code": current_code, "to_stage_code": "sent_to_department"},
            ) from error
        try:
            attempt, created = repo.create_handoff_attempt(
                session,
                application_id=application.id,
                stage_event_id=event.id,
                recipient_user_id=recipient_user_id,
                recipient_name=recipient_name,
                recipient_department=recipient_department,
                channel=handoff_in.channel,
                handed_off_at=handed_off_at,
                created_by_user_id=user.id,
                summary_revision=summary.summary_revision,
                summary_snapshot=snapshot,
                request_id=handoff_in.request_id,
            )
        except repo.RequestIdReusedError as error:
            raise ApiError(409, "REQUEST_ID_REUSED", str(error), {}) from error
    session.commit()

    stages = workflow._stages(session)
    return (
        StageMoveOut(
            application_id=application.id,
            stage=workflow.stage_out(stages[application.current_stage_code]),
            event=workflow._event_out(event, stages, workflow._reasons(session), {user.id: user}),
            handoff=_attempt_out(session, attempt, as_of=datetime.now(timezone.utc)),
        ),
        created,
    )


def create_additional_handoff(
    session: Session,
    application_id: uuid.UUID,
    body: HandoffCreateIn,
    user: User,
) -> HandoffCreatedOut:
    """Создать ещё одну попытку передачи другому получателю, когда отклик уже в департаменте."""
    application = workflow.get_application_or_404(session, application_id)
    workflow.require_working_application(application)
    handoff_in = body.handoff
    recipient_user_id, recipient_name, recipient_department = _resolve_recipient(session, handoff_in)

    session.refresh(application, with_for_update=True)
    existing_attempt = session.scalar(
        select(HandoffAttempt).where(HandoffAttempt.request_id == handoff_in.request_id)
    )
    if existing_attempt is not None:
        if existing_attempt.stage_event_id is None and repo._handoff_matches(
            existing_attempt,
            application_id=application.id,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            recipient_department=recipient_department,
            channel=handoff_in.channel,
            summary_revision=handoff_in.summary_revision,
        ):
            return HandoffCreatedOut(
                created=False,
                attempt=_attempt_out(session, existing_attempt, as_of=datetime.now(timezone.utc)),
            )
        raise ApiError(409, "REQUEST_ID_REUSED", "request_id уже использован для другой передачи", {})

    if application.current_stage_code not in ("sent_to_department", "department_interview"):
        raise ApiError(
            409,
            "HANDOFF_STAGE_REQUIRED",
            "Дополнительная передача возможна только на этапах рассмотрения департаментом",
            {"current_stage_code": application.current_stage_code},
        )
    current_seq = workflow.last_seq(session, application.id)
    if current_seq != body.expected_seq:
        raise ApiError(
            409,
            "STALE_STAGE_FORM",
            "Отклик уже изменён в другом окне: обновите карточку",
            {
                "expected_seq": body.expected_seq,
                "last_seq": current_seq,
                "current_stage_code": application.current_stage_code,
            },
        )

    recipient_user_id, recipient_name, recipient_department, handed_off_at, summary = _validate_and_prepare_handoff(
        session, application, handoff_in
    )
    snapshot = {
        "summary": summary.summary.model_dump(mode="json"),
        "markdown": summary.markdown,
        "referenced_text_ids": summary.summary.referenced_text_ids,
    }
    try:
        attempt, created = repo.create_handoff_attempt(
            session,
            application_id=application.id,
            stage_event_id=None,
            recipient_user_id=recipient_user_id,
            recipient_name=recipient_name,
            recipient_department=recipient_department,
            channel=handoff_in.channel,
            handed_off_at=handed_off_at,
            created_by_user_id=user.id,
            summary_revision=summary.summary_revision,
            summary_snapshot=snapshot,
            request_id=handoff_in.request_id,
        )
    except repo.RequestIdReusedError as error:
        raise ApiError(409, "REQUEST_ID_REUSED", str(error), {}) from error
    session.commit()
    return HandoffCreatedOut(
        created=created,
        attempt=_attempt_out(session, attempt, as_of=datetime.now(timezone.utc)),
    )


def _assemble_attempt_list(session: Session, attempts: list[HandoffAttempt], as_of: datetime) -> list[HandoffAttemptOut]:
    if not attempts:
        return []
    attempt_ids = [a.id for a in attempts]
    feedbacks = list(
        session.scalars(
            select(DepartmentFeedback)
            .where(DepartmentFeedback.attempt_id.in_(attempt_ids))
            .order_by(DepartmentFeedback.revision)
        )
    )
    fb_by_attempt: dict[uuid.UUID, list[DepartmentFeedback]] = defaultdict(list)
    user_ids: set[uuid.UUID | None] = set()
    for a in attempts:
        user_ids.add(a.recipient_user_id)
        user_ids.add(a.created_by_user_id)
    for fb in feedbacks:
        if fb.attempt_id is not None:
            fb_by_attempt[fb.attempt_id].append(fb)
        user_ids.add(fb.reported_by_user_id)
        user_ids.add(fb.author_user_id)
    reasons = workflow._reasons(session)
    users = workflow._users(session, user_ids)
    return [
        _attempt_out(
            session,
            attempt,
            as_of=as_of,
            feedback_by_attempt=fb_by_attempt,
            reasons=reasons,
            users=users,
        )
        for attempt in attempts
    ]


def list_handoffs(
    session: Session,
    user: User,
    *,
    contour: Contour = Contour.WORKING,
    status: HandoffStatus | None = None,
    department: str | None = None,
    recipient_user_id: uuid.UUID | None = None,
    actor_login: str | None = None,
    vacancy_id: uuid.UUID | None = None,
    position_id: uuid.UUID | None = None,
) -> HandoffListOut:
    """Очередь передач: все в контуре для HR/admin, только свои для department."""
    if user.role == UserRole.DEPARTMENT:
        if recipient_user_id is not None and recipient_user_id != user.id:
            raise ApiError(
                403,
                "FORBIDDEN_SCOPE",
                "Доступ разрешён только к собственным передачам",
                {},
            )
        recipient_user_id = user.id

    as_of = datetime.now(timezone.utc)
    stmt = (
        select(HandoffAttempt)
        .join(Application, Application.id == HandoffAttempt.application_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(
            Application.source == ApplicationSource.RESPONSE,
            Candidate.is_synthetic == (contour == Contour.TRAINING),
        )
        .order_by(HandoffAttempt.handed_off_at.desc(), HandoffAttempt.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(HandoffAttempt.status == status)
    if _clean(department) is not None:
        stmt = stmt.where(HandoffAttempt.recipient_department == _clean(department))
    if recipient_user_id is not None:
        stmt = stmt.where(HandoffAttempt.recipient_user_id == recipient_user_id)
    if _clean(actor_login) is not None:
        actor = session.scalar(select(User).where(User.login == _clean(actor_login)))
        if actor is None:
            return HandoffListOut(as_of=as_of, total=0, items=[])
        stmt = stmt.where(HandoffAttempt.created_by_user_id == actor.id)
    if vacancy_id is not None:
        stmt = stmt.where(Application.vacancy_id == vacancy_id)
    if position_id is not None:
        stmt = stmt.where(Vacancy.position_id == position_id)

    attempts = list(session.scalars(stmt))
    items = _assemble_attempt_list(session, attempts, as_of)
    return HandoffListOut(as_of=as_of, total=len(items), items=items)


def list_application_handoffs(session: Session, application_id: uuid.UUID, user: User) -> HandoffListOut:
    """Все попытки передачи отклика (для department — только назначенные ему)."""
    if user.role == UserRole.DEPARTMENT and not repo.has_department_application_access(
        session, user.id, application_id
    ):
        raise ApiError(
            403,
            "FORBIDDEN_SCOPE",
            "Доступ разрешён только к переданным откликам",
            {"application_id": str(application_id)},
        )
    workflow.get_application_or_404(session, application_id)
    as_of = datetime.now(timezone.utc)
    stmt = (
        select(HandoffAttempt)
        .where(HandoffAttempt.application_id == application_id)
        .order_by(HandoffAttempt.handed_off_at.desc(), HandoffAttempt.created_at.desc())
    )
    if user.role == UserRole.DEPARTMENT:
        stmt = stmt.where(HandoffAttempt.recipient_user_id == user.id)
    attempts = list(session.scalars(stmt))
    items = _assemble_attempt_list(session, attempts, as_of)
    return HandoffListOut(as_of=as_of, total=len(items), items=items)


def get_handoff_detail(session: Session, attempt_id: uuid.UUID, user: User) -> HandoffAttemptDetailOut:
    """Карточка попытки передачи: замороженный снимок сводки и история ответов."""
    attempt = session.get(HandoffAttempt, attempt_id)
    if user.role == UserRole.DEPARTMENT:
        if attempt is None or attempt.recipient_user_id != user.id:
            raise ApiError(
                403,
                "FORBIDDEN_SCOPE",
                "Доступ разрешён только к собственным передачам",
                {"attempt_id": str(attempt_id)},
            )
    elif attempt is None:
        raise not_found("HANDOFF_NOT_FOUND", "Передача не найдена", attempt_id=attempt_id)
    as_of = datetime.now(timezone.utc)
    rows = list(
        session.scalars(
            select(DepartmentFeedback)
            .where(DepartmentFeedback.attempt_id == attempt.id)
            .order_by(DepartmentFeedback.revision, DepartmentFeedback.received_at)
        )
    )
    reasons = workflow._reasons(session)
    uid_set = {attempt.recipient_user_id, attempt.created_by_user_id}
    for row in rows:
        uid_set.update([row.reported_by_user_id, row.author_user_id])
    users = workflow._users(session, uid_set)
    base = _attempt_out(
        session,
        attempt,
        as_of=as_of,
        feedback_by_attempt={attempt.id: rows},
        reasons=reasons,
        users=users,
    )
    history = [
        _feedback_out(row, reasons, users, is_current=(idx == len(rows) - 1))
        for idx, row in enumerate(rows)
    ]
    return HandoffAttemptDetailOut(
        **base.model_dump(),
        summary=HandoffSummaryPayloadOut.model_validate(attempt.summary_snapshot["summary"]),
        markdown=attempt.summary_snapshot["markdown"],
        feedback_history=history,
    )


def record_feedback(
    session: Session,
    application_id: uuid.UUID,
    body: HandoffFeedbackIn,
    user: User,
) -> HandoffFeedbackCreatedOut:
    """Записать ответ департамента или его исправление (этап отклика не меняется)."""
    attempt = session.get(HandoffAttempt, body.attempt_id)
    if user.role == UserRole.DEPARTMENT:
        if attempt is None or attempt.recipient_user_id != user.id or attempt.application_id != application_id:
            raise ApiError(
                403,
                "FORBIDDEN_SCOPE",
                "Отзыв доступен только назначенному получателю передачи",
                {"attempt_id": str(body.attempt_id)},
            )

    application = workflow.get_application_or_404(session, application_id)
    workflow.require_working_application(application)
    if attempt is None:
        raise not_found("HANDOFF_NOT_FOUND", "Передача не найдена", attempt_id=body.attempt_id)
    if attempt.application_id != application.id:
        raise ApiError(
            422,
            "ATTEMPT_OF_OTHER_APPLICATION",
            "Указанная передача относится к другому отклику",
            {"attempt_id": str(attempt.id)},
        )

    interview_status = body.interview_status
    if body.interview_held is not None and body.interview_status == ProcessFactStatus.NOT_REPORTED:
        interview_status = ProcessFactStatus.YES if body.interview_held else ProcessFactStatus.NO

    if body.outcome == FeedbackOutcome.NOT_FIT:
        reason_code = _clean(body.rejection_reason_code)
        if reason_code is None:
            raise ApiError(
                422,
                "REJECTION_REASON_REQUIRED",
                "Для отрицательного ответа укажите причину по справочнику",
                {},
            )
        if session.get(RejectionReason, reason_code) is None:
            raise ApiError(
                422,
                "UNKNOWN_REJECTION_REASON",
                "Неизвестная причина отказа",
                {"rejection_reason_code": reason_code},
            )
    else:
        reason_code = None
        if body.rejection_reason_code is not None:
            raise ApiError(
                422,
                "REJECTION_REASON_NOT_ALLOWED",
                "Причина отказа указывается только для исхода not_fit",
                {"outcome": str(body.outcome)},
            )

    if user.role == UserRole.DEPARTMENT:
        response_channel = HandoffChannel.CABINET
        reported_by_user_id: uuid.UUID | None = user.id
        reported_by_name: str | None = user.full_name
        reported_at = _utc(body.reported_at) if body.reported_at else None
    else:
        if body.response_channel is None:
            raise ApiError(
                422,
                "FEEDBACK_SOURCE_REQUIRED",
                "При регистрации внешнего ответа укажите канал поступления (response_channel)",
                {},
            )
        reported_by_user_id = body.reported_by_user_id
        reported_user = session.get(User, reported_by_user_id) if reported_by_user_id else None
        if reported_by_user_id is not None and reported_user is None:
            raise not_found("USER_NOT_FOUND", "Автор ответа не найден", user_id=reported_by_user_id)
        reported_by_name = _clean(body.reported_by_name) or (reported_user.full_name if reported_user else None)
        if reported_by_name is None:
            raise ApiError(
                422,
                "FEEDBACK_SOURCE_REQUIRED",
                "Укажите имя автора или источник полученного ответа",
                {},
            )
        response_channel = body.response_channel
        reported_at = _utc(body.reported_at) if body.reported_at else None

    if body.supersedes_id is not None:
        prev = session.get(DepartmentFeedback, body.supersedes_id)
        if prev is None:
            raise not_found("FEEDBACK_NOT_FOUND", "Исправляемый отзыв не найден", feedback_id=body.supersedes_id)
        if prev.attempt_id != attempt.id:
            raise ApiError(
                422,
                "FEEDBACK_OF_OTHER_ATTEMPT",
                "Исправляемый отзыв относится к другой передаче",
                {"supersedes_id": str(body.supersedes_id)},
            )

    try:
        fb, created = repo.record_handoff_feedback(
            session,
            application_id=application.id,
            attempt_id=attempt.id,
            outcome=body.outcome,
            contact_status=body.contact_status,
            interview_status=interview_status,
            confirmed_competencies=[c.strip() for c in body.confirmed_competencies if c.strip()],
            gaps=_clean(body.gaps),
            rejection_reason_code=reason_code,
            keep_in_reserve=body.keep_in_reserve,
            comment=_clean(body.comment),
            response_channel=response_channel,
            reported_by_user_id=reported_by_user_id,
            reported_by_name=reported_by_name,
            reported_at=reported_at,
            author_user_id=user.id,
            supersedes_id=body.supersedes_id,
            request_id=body.request_id,
        )
    except repo.RequestIdReusedError as error:
        raise ApiError(409, "REQUEST_ID_REUSED", str(error), {}) from error
    except repo.FeedbackConflictError as error:
        raise ApiError(
            409,
            "FEEDBACK_CONFLICT",
            str(error),
            {
                "current_feedback_id": str(error.current_feedback_id),
                "current_revision": error.current_revision,
            },
        ) from error
    except repo.RepositoryError as error:
        raise ApiError(422, "VALIDATION_ERROR", str(error), {}) from error

    session.commit()
    session.refresh(fb)
    has_newer = (
        session.scalar(
            select(DepartmentFeedback.id)
            .where(DepartmentFeedback.supersedes_id == fb.id)
            .limit(1)
        )
        is not None
    )
    reasons = workflow._reasons(session)
    users = workflow._users(session, [fb.reported_by_user_id, fb.author_user_id])
    return HandoffFeedbackCreatedOut(
        created=created,
        feedback=_feedback_out(fb, reasons, users, is_current=not has_newer),
    )


def list_feedback(
    session: Session,
    application_id: uuid.UUID,
    user: User,
    *,
    attempt_id: uuid.UUID | None = None,
) -> HandoffFeedbackListOut:
    """История ответов департамента по отклику (для department — только по своим передачам)."""
    if user.role == UserRole.DEPARTMENT and not repo.has_department_application_access(
        session, user.id, application_id
    ):
        raise ApiError(
            403,
            "FORBIDDEN_SCOPE",
            "Отзывы доступны только по переданным вам откликам",
            {"application_id": str(application_id)},
        )
    application = workflow.get_application_or_404(session, application_id)

    stmt = (
        select(DepartmentFeedback)
        .where(DepartmentFeedback.application_id == application.id)
        .order_by(DepartmentFeedback.received_at, DepartmentFeedback.revision, DepartmentFeedback.id)
    )
    if attempt_id is not None:
        attempt = session.get(HandoffAttempt, attempt_id)
        if user.role == UserRole.DEPARTMENT:
            if attempt is None or attempt.recipient_user_id != user.id or attempt.application_id != application.id:
                raise ApiError(403, "FORBIDDEN_SCOPE", "Нет доступа к отзывам чужой передачи", {})
        elif attempt is None:
            raise not_found("HANDOFF_NOT_FOUND", "Передача не найдена", attempt_id=attempt_id)
        elif attempt.application_id != application.id:
            raise ApiError(
                422,
                "ATTEMPT_OF_OTHER_APPLICATION",
                "Указанная передача относится к другому отклику",
                {"attempt_id": str(attempt_id)},
            )
        stmt = stmt.where(DepartmentFeedback.attempt_id == attempt_id)
    elif user.role == UserRole.DEPARTMENT:
        own_attempt_ids = select(HandoffAttempt.id).where(
            HandoffAttempt.application_id == application.id,
            HandoffAttempt.recipient_user_id == user.id,
        )
        stmt = stmt.where(DepartmentFeedback.attempt_id.in_(own_attempt_ids))

    rows = list(session.scalars(stmt))
    max_rev_by_attempt: dict[uuid.UUID, int] = {}
    for row in rows:
        if row.attempt_id is not None:
            max_rev_by_attempt[row.attempt_id] = max(max_rev_by_attempt.get(row.attempt_id, 0), row.revision)

    reasons = workflow._reasons(session)
    users = workflow._users(
        session, [uid for row in rows for uid in (row.reported_by_user_id, row.author_user_id)]
    )
    items = [
        _feedback_out(
            row,
            reasons,
            users,
            is_current=(row.attempt_id is None or row.revision == max_rev_by_attempt.get(row.attempt_id)),
        )
        for row in rows
    ]
    return HandoffFeedbackListOut(application_id=application.id, total=len(items), items=items)


def funnel_open_waits(
    session: Session,
    scope_ids,
    *,
    as_of: datetime,
    department: str | None = None,
) -> OpenWaitsOut:
    """Посчитать открытые ожидания ответов департамента в выборке воронки на момент as_of."""
    stmt = select(HandoffAttempt).where(
        HandoffAttempt.application_id.in_(scope_ids),
        HandoffAttempt.status == HandoffStatus.AWAITING_RESPONSE,
    )
    cleaned_dep = _clean(department)
    if cleaned_dep is not None:
        stmt = stmt.where(HandoffAttempt.recipient_department == cleaned_dep)
    rows = list(session.scalars(stmt))
    if not rows:
        return OpenWaitsOut(total=0, unique_applications=0, max_wait_hours=None, median_wait_hours=None, by_department=[])

    as_of_utc = _utc(as_of)
    hours = [max(0.0, round((as_of_utc - _utc(r.handed_off_at)).total_seconds() / 3600.0, 2)) for r in rows]
    grouped: dict[str, list[tuple[uuid.UUID, float]]] = defaultdict(list)
    for row, h in zip(rows, hours):
        grouped[row.recipient_department].append((row.application_id, h))

    by_department = [
        OpenWaitsByDepartmentOut(
            department=dep,
            total=len(items),
            unique_applications=len({app_id for app_id, _ in items}),
            max_wait_hours=round(max(h for _, h in items), 2),
            median_wait_hours=round(float(median(h for _, h in items)), 2),
        )
        for dep, items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    ]
    return OpenWaitsOut(
        total=len(rows),
        unique_applications=len({r.application_id for r in rows}),
        max_wait_hours=round(max(hours), 2),
        median_wait_hours=round(float(median(hours)), 2),
        by_department=by_department,
    )
