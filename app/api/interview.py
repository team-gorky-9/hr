"""Гайд интервью, ответы и подтверждение требования (контракт interview.md v0.4, §4; задача interview-01).

Сборку гайда (пробелы кодом, вопросы моделью) делает app.interview.build_guide (Илья), правила
хранения — app/db/repository.py. Здесь — то, что добавляет HTTP:
- права: все маршруты — кадровик или администратор (StaffUser). Роль department получает 403,
  пока workflow-01 не введёт назначение получателя (v0.4, §4 «Кто что может»);
- какая оценка у отклика — та же, что в карточке (цель из реестра публикаций + resolve_states), и коды ошибок;
- транзакции POST гайда: сборка и вызов модели в сессии только для чтения, затем отдельная короткая
  транзакция записи с перепроверкой оценки (409 ASSESSMENT_CHANGED). Сессия чтения держит
  соединение пула на время вызова модели — это допущение v0.4;
- что считается при чтении: устаревание гайда, статус вопросов, запросы документов.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import LLMClient, build_client
from app.ai.errors import LLMInvalidResponseError, LLMUnavailableError
from app.api.errors import ApiError, not_found
from app.api.schemas import (
    AnswerIn,
    AnswerListOut,
    AnswerOut,
    AssessmentOut,
    ConfirmIn,
    CriterionOut,
    DocumentRequestOut,
    InterviewGuideIn,
    InterviewGuideOut,
    InterviewListOut,
    InterviewOut,
    InterviewOutcomeIn,
    InterviewQuestionOut,
    InterviewUserOut,
    ResolvedByOut,
)
from app.api.services import assessment_out
from app.api.workflow import get_application_or_404, require_working_application
from app.assessment.service import record_llm_calls
from app.assessment.state import AssessmentState, AssessmentStatus, resolve_states
from app.db import repository as repo
from app.db.enums import AnswerSource, AuditAction, CheckResult, InterviewKind, InterviewResult, InterviewQuestionKind, RubricStatus, VerificationMethod
from app.db.models import (
    Application,
    Assessment,
    Candidate,
    CandidateCard,
    Interview,
    InterviewAnswer,
    InterviewGuide,
    InterviewQuestion,
    InterviewRubricQuestion,
    Position,
    RequirementProfile,
    User,
    Vacancy,
)
from app.interview import build_guide
from app.interview.gaps import assemble_gaps
from app.interview.generate import GUIDE_PROMPT_VERSION, QuestionItem
from app.interview.service import GuideError
from app.postings.service import ApplicationResolution, resolve_application, resolved_state


class _LazyLLMClient:
    """Клиент создаётся при первом обращении к модели, а не при разборе запроса.

    Иначе стенд без ключа модели отвечал 500 на любой POST гайда: build_client бросал
    LLMUnavailableError ещё в зависимости FastAPI, до проверки оценки. Теперь отклик без оценки
    получает 409 ASSESSMENT_REQUIRED, а отсутствие ключа при нужном вызове — 503 LLM_UNAVAILABLE."""

    def __init__(self):
        self._client: LLMClient | None = None

    def __getattr__(self, name: str):
        if name == "calls" and self._client is None:
            return []  # журнал вызовов пуст, пока модель не понадобилась (гайд из кэша рубрики)
        if self._client is None:
            self._client = build_client()
        return getattr(self._client, name)


def get_llm_client() -> LLMClient:
    """Клиент модели для маршрута гайда; в тестах подменяется FakeLLMClient через dependency_overrides."""
    return _LazyLLMClient()


def rule_error(error: repo.RuleConflict) -> ApiError:
    """Нарушенное правило хранения → ответ API с кодом из контракта."""
    return ApiError(404 if error.not_found else 409, error.code, _sentence(str(error)), error.details)


def _sentence(text: str) -> str:
    text = text.strip()
    return (text[:1].upper() + text[1:]) if text else text


# --- Какая оценка у отклика -------------------------------------------------------------

@dataclass
class ApplicationContext:
    application: Application
    candidate: Candidate
    profile: RequirementProfile | None   # утверждённый профиль должности в контуре кандидата
    state: AssessmentState               # как в карточке отклика, с учётом применимости
    resolution: ApplicationResolution    # решение реестра по этому отклику


def application_context(session: Session, application: Application) -> ApplicationContext:
    """Профиль и оценка отклика — тем же путём, что карточка (services.get_application):
    подтверждённая цель отклика из реестра публикаций (requirements-03) → утверждённый профиль
    должности в контуре кандидата → resolve_states. Неготовая цель даёт not_applicable,
    mapping_required или no_approved_profile."""
    candidate = session.get(Candidate, application.candidate_id)
    vacancy = session.get(Vacancy, application.vacancy_id) if application.vacancy_id else None
    position = session.get(Position, vacancy.position_id) if vacancy else None
    resolution = resolve_application(session, application.id)
    state = resolved_state(session, resolution, imported_position_code=position.code if position else None)
    profile = session.get(RequirementProfile, resolution.profile_id) if resolution.profile_id else None
    return ApplicationContext(application, candidate, profile, state, resolution)


def require_ready_assessment(context: ApplicationContext) -> Assessment:
    """Гайд строится только по актуальной оценке отклика (таблица ошибок §4)."""
    status = context.state.status
    if status == AssessmentStatus.READY:
        return context.state.assessment
    if status == AssessmentStatus.NO_APPROVED_PROFILE:
        raise ApiError(409, "NO_APPROVED_PROFILE", "У вакансии нет утверждённого профиля в этом контуре")
    if status in (AssessmentStatus.NOT_APPLICABLE, AssessmentStatus.MAPPING_REQUIRED):
        details = {"assessment_status": str(status), "resolution_reason": context.resolution.reason}
        if status == AssessmentStatus.MAPPING_REQUIRED:
            raise ApiError(409, "MAPPING_REQUIRED",
                           "Публикация этого отклика ещё не сопоставлена с должностью. "
                           + context.resolution.mapping.explanation, details)
        raise ApiError(409, "NOT_APPLICABLE",
                       "По решению реестра профиль этой должности неприменим к публикации отклика.", details)
    if status == AssessmentStatus.STALE:
        raise ApiError(409, "ASSESSMENT_STALE", "Оценка устарела: переоцените отклик",
                       {"stale_reason": str(context.state.stale_reason)})
    raise ApiError(409, "ASSESSMENT_REQUIRED", "Сначала оцените отклик")


def _profile_with_rows(session: Session, profile_id: uuid.UUID) -> RequirementProfile:
    """Профиль с требованиями и компетенциями — их читает сборщик пробелов."""
    profile = session.get(RequirementProfile, profile_id)
    _ = profile.formal_requirements, [c.indicators for c in profile.competencies]
    return profile


def _card_missing(session: Session, assessment: Assessment) -> list[str]:
    card = session.get(CandidateCard, assessment.card_id)
    return list((card.card or {}).get("missing") or []) if card else []


# --- POST гайда -------------------------------------------------------------------------

def create_guide(
    session: Session, application_id: uuid.UUID, body: InterviewGuideIn, user: User, llm: LLMClient
) -> tuple[InterviewGuideOut, bool]:
    """Сформировать или вернуть гайд. Вернуть (гайд, создана ли новая версия): 201 / 200.

    1. Повтор request_id — тот же гайд и тот же статус ответа, без вызова модели.
    2. Гайд у открытой встречи есть и regenerate = false — последняя версия, без модели.
    3. regenerate = true и основание не изменилось (базовая оценка, профиль, рубрика) — текущая версия.
    4. Иначе: сборка и модель в сессии чтения → rollback → короткая транзакция записи.
    """
    kind = InterviewKind(body.kind)
    application = get_application_or_404(session, application_id)
    require_working_application(application)

    replay = repo.find_guide_by_request(session, body.request_id)
    if replay is not None:
        try:
            repo.check_guide_request(session, replay, application.id, kind)
        except repo.RuleConflict as error:
            raise rule_error(error) from error
        return guide_out(session, replay), True

    interview = session.scalar(select(Interview).where(
        Interview.application_id == application.id, Interview.kind == kind, Interview.result == "pending"))
    existing = repo.latest_guide(session, interview.id) if interview else None
    if existing is not None and not body.regenerate:
        return guide_out(session, existing), False

    context = application_context(session, application)
    assessment = require_ready_assessment(context)
    profile = _profile_with_rows(session, assessment.profile_id)
    if existing is not None and _basis_unchanged(session, existing, assessment, profile):
        return guide_out(session, existing), False

    # --- Чтение и вызов модели: ничего не пишем, блокировок не берём. ---
    snapshot = (assessment.id, assessment.base_id, profile.id)
    cached_rubric = repo.rubric_for_profile(session, profile.id)
    rubric_state = {key: (row.version, str(row.status)) for key, row in cached_rubric.items()}
    core_cache = {key: QuestionItem(ref=key, question=row.question,
                                    good_answer=row.criterion.get("good_answer", "—"),
                                    insufficient_answer=row.criterion.get("insufficient_answer", "—"))
                  for key, row in cached_rubric.items()}
    try:
        draft = build_guide(session, assessment_id=assessment.id, llm=llm, core_cache=core_cache, record_calls=False)
    except GuideError as error:
        session.rollback()
        raise ApiError(409, error.reason.upper(), _sentence(str(error))) from error
    except LLMUnavailableError as error:
        session.rollback()
        raise ApiError(503, "LLM_UNAVAILABLE", "Модель недоступна: новый гайд не создан, прежний доступен по GET") from error
    except LLMInvalidResponseError as error:
        session.rollback()
        raise ApiError(502, "LLM_INVALID_RESPONSE",
                       "Модель вернула ответ не по схеме: новый гайд не создан, прежний доступен по GET") from error
    gap_titles = {g.gap_ref_id: g.title
                  for g in assemble_gaps(profile, assessment, _card_missing(session, assessment), budget=10_000).selected}
    session.rollback()  # конец чтения: соединение больше не держит снимок

    # --- Короткая транзакция записи. ---
    application = get_application_or_404(session, application_id)
    context = application_context(session, application)
    current = context.state.assessment if context.state.status == AssessmentStatus.READY else None
    if current is None or (current.id, current.base_id, current.profile_id) != snapshot:
        session.rollback()
        raise ApiError(409, "ASSESSMENT_CHANGED", "Оценка изменилась, пока готовился гайд: повторите запрос")
    rubric_now = repo.rubric_for_profile(session, snapshot[2])
    if any((rubric_now[key].version, str(rubric_now[key].status)) != state
           for key, state in rubric_state.items() if key in rubric_now):
        session.rollback()
        raise ApiError(409, "ASSESSMENT_CHANGED", "Рубрику ядра изменили, пока готовился гайд: повторите запрос",
                       {"reason": "rubric_changed"})

    new_rows = [_rubric_item(q) for q in draft.core if _row_key(q) not in rubric_now]
    rubric = repo.save_rubric_questions(session, snapshot[2], new_rows) if new_rows else rubric_now
    core_rows = [rubric[_row_key(q)] for q in draft.core]
    questions = [_core_question(q, rubric[_row_key(q)]) for q in draft.core]
    questions += [_clarification_question(q, gap_titles.get(q["gap_ref_id"])) for q in draft.clarifications]

    interview = repo.open_interview(session, application.id, kind)
    try:
        guide, created = repo.save_interview_guide(
            session,
            interview=interview,
            base_assessment_id=snapshot[1],
            profile_id=snapshot[2],
            rubric_version=repo.rubric_fingerprint(core_rows),
            prompt_version=draft.prompt_version or GUIDE_PROMPT_VERSION,
            model_calls=draft.model_calls,
            uncovered_gaps=draft.uncovered_gaps,
            request_id=body.request_id,
            created_by_user_id=user.id,
            questions=questions,
        )
    except repo.RuleConflict as error:
        session.rollback()
        raise rule_error(error) from error
    record_llm_calls(session, llm, context.candidate.id)
    session.commit()
    return guide_out(session, guide), created


def _basis_unchanged(session: Session, guide: InterviewGuide, assessment: Assessment,
                     profile: RequirementProfile) -> bool:
    """Та же базовая оценка, версия профиля и рубрика ядра — перегенерация ничего не изменит."""
    return (guide.assessment_id == assessment.base_id and guide.profile_id == profile.id
            and _rubric_unchanged(session, guide))


def _rubric_unchanged(session: Session, guide: InterviewGuide) -> bool:
    rubric_ids = [q.rubric_question_id for q in repo.guide_questions(session, guide.id) if q.rubric_question_id]
    rows = list(session.scalars(select(InterviewRubricQuestion).where(InterviewRubricQuestion.id.in_(rubric_ids)))) \
        if rubric_ids else []
    return repo.rubric_fingerprint(rows) == guide.rubric_version


def _row_key(question: dict[str, Any]) -> str:
    return question["sources"][0]["key"]


def _rubric_item(question: dict[str, Any]) -> dict[str, Any]:
    source = question["sources"][0]
    return {
        "row_key": source["key"],
        "requirement_id": uuid.UUID(source["requirement_id"]) if source.get("requirement_id") else None,
        "indicator_key": None if source.get("requirement_id") else source["key"],
        "question": question["question"],
        "criterion": question["criterion"],
    }


def _core_question(question: dict[str, Any], row: InterviewRubricQuestion) -> dict[str, Any]:
    """Вопрос ядра берётся из сохранённой строки рубрики: так он одинаков у всех кандидатов,
    даже если параллельный запрос записал строку раньше нас."""
    source = question["sources"][0]
    return {
        "kind": InterviewQuestionKind.CORE,
        "sort_order": question["sort_order"],
        "question": row.question,
        "criterion": row.criterion,
        "author": row.author,
        "gap": None,
        "gap_ref_id": None,
        "sources": question["sources"],
        "requirement_id": row.requirement_id,
        "indicator_key": row.indicator_key,
        "competency_id": uuid.UUID(source["competency_id"]) if source.get("competency_id") else None,
        "rubric_question_id": row.id,
    }


def _clarification_question(question: dict[str, Any], title: str | None) -> dict[str, Any]:
    sources = question["sources"]
    formal = next((s for s in sources if s.get("type") == "formal_check"), None)
    indicator = next((s for s in sources if s.get("type") in ("indicator", "group")), None)
    return {
        "kind": InterviewQuestionKind.CLARIFICATION,
        "sort_order": question["sort_order"],
        "question": question["question"],
        "criterion": question["criterion"],
        "author": question.get("author", "model"),
        "gap": title,
        "gap_ref_id": question["gap_ref_id"],
        "sources": sources,
        "requirement_id": uuid.UUID(formal["requirement_id"]) if formal else None,
        "indicator_key": indicator["key"] if indicator and indicator.get("type") == "indicator" else None,
        "competency_id": uuid.UUID(indicator["competency_id"]) if indicator else None,
        "rubric_question_id": None,
    }


# --- GET гайда и сборка ответа -------------------------------------------------------------

def get_guide(session: Session, application_id: uuid.UUID, kind: InterviewKind,
              guide_version: int | None) -> InterviewGuideOut:
    application = get_application_or_404(session, application_id)
    interview = repo.latest_interview(session, application.id, kind)
    guide = None
    if interview is not None:
        guide = (repo.get_guide_version(session, interview.id, guide_version) if guide_version is not None
                 else repo.latest_guide(session, interview.id))
    if guide is None:
        raise not_found("GUIDE_NOT_FOUND", "Гайд не найден", application_id=application_id, kind=str(kind))
    return guide_out(session, guide)


def guide_out(session: Session, guide: InterviewGuide) -> InterviewGuideOut:
    """Снимок версии гайда плюс то, что считается по текущей оценке пары (§4 «Что снимок…»)."""
    interview = session.get(Interview, guide.interview_id)
    application = session.get(Application, interview.application_id)
    context = application_context(session, application)
    guide_profile = session.get(RequirementProfile, guide.profile_id) if guide.profile_id else None
    base = session.get(Assessment, guide.assessment_id) if guide.assessment_id else None

    # Текущая оценка той же пары (кандидат × профиль гайда).
    current = None
    if guide_profile is not None:
        current = session.scalar(select(Assessment).where(
            Assessment.candidate_id == context.candidate.id, Assessment.profile_id == guide_profile.id,
            Assessment.is_current))

    stale_reason = None
    if not guide.is_migrated:
        if context.profile is None or guide_profile is None or context.profile.id != guide_profile.id:
            stale_reason = "profile_changed"
        elif context.state.status == AssessmentStatus.STALE:
            stale_reason = "assessment_stale"
        elif current is None or current.base_id != guide.assessment_id:
            stale_reason = "assessment_changed"
        elif not _rubric_unchanged(session, guide):
            stale_reason = "rubric_changed"

    questions = repo.guide_questions(session, guide.id)
    checks = {c.requirement_id: c for c in current.formal_checks} if current else {}
    users = _users(session, {c.confirmed_by_user_id for c in checks.values()} | {guide.created_by_user_id})
    items = [_question_out(session, q, checks, current, users) for q in questions]

    document_requests: list[DocumentRequestOut] = []
    if current is not None and guide_profile is not None:
        plan = assemble_gaps(_profile_with_rows(session, guide_profile.id), current, _card_missing(session, current))
        document_requests = [DocumentRequestOut(**r) for r in plan.document_requests]

    rubric_ids = [q.rubric_question_id for q in questions if q.rubric_question_id]
    rubric_status = None
    if rubric_ids:
        statuses = set(session.scalars(select(InterviewRubricQuestion.status)
                                       .where(InterviewRubricQuestion.id.in_(rubric_ids))))
        rubric_status = "approved" if statuses == {RubricStatus.APPROVED} else "draft"

    return InterviewGuideOut(
        interview_id=interview.id,
        guide_id=guide.id,
        application_id=application.id,
        kind=str(interview.kind),
        guide_version=guide.guide_version,
        is_training=bool(context.candidate.is_synthetic or (guide_profile is not None and guide_profile.is_synthetic)),
        assessment_id=guide.assessment_id,
        assessment_version=base.version if base else None,
        current_assessment_id=current.id if current else None,
        profile_id=guide.profile_id,
        profile_version=guide_profile.version if guide_profile else None,
        rubric_status=rubric_status,
        is_stale=stale_reason is not None,
        stale_reason=stale_reason,
        prompt_version=guide.prompt_version,
        model_calls=guide.model_calls,
        created_at=guide.created_at,
        created_by=_user_out(users.get(guide.created_by_user_id)),
        core=[i for i in items if i.kind == InterviewQuestionKind.CORE],
        clarifications=[i for i in items if i.kind != InterviewQuestionKind.CORE],
        document_requests=document_requests,
        uncovered_gaps=guide.uncovered_gaps or [],
    )


def _question_requirements(question: InterviewQuestion) -> list[uuid.UUID]:
    """Формальные требования из источников вопроса: их закрывает confirm."""
    ids = []
    for source in question.sources or []:
        if source.get("requirement_id") and source.get("type") in ("formal_check", "profile_row"):
            ids.append(uuid.UUID(source["requirement_id"]))
    return list(dict.fromkeys(ids))


def _question_out(session: Session, question: InterviewQuestion, checks: dict, current: Assessment | None,
                  users: dict[uuid.UUID, User]) -> InterviewQuestionOut:
    """Статус считается при чтении (§4): resolved — по всем формальным требованиям вопроса есть
    результат не по резюме; answered — ответ есть, а подтверждения нет или оно не предусмотрено;
    open — ответа нет."""
    answer, carried = repo.visible_answer(session, question)
    requirement_ids = _question_requirements(question)
    confirmed = [checks[r] for r in requirement_ids if r in checks and checks[r].basis != VerificationMethod.RESUME]
    status, resolved_by = "open", None
    if requirement_ids and current is not None and len(confirmed) == len(requirement_ids):
        status = "resolved"
        first = confirmed[0]
        confirmer = users.get(first.confirmed_by_user_id) or session.get(User, first.confirmed_by_user_id)
        resolved_by = ResolvedByOut(
            assessment_id=current.id, assessment_version=current.version, requirement_id=first.requirement_id,
            result=CheckResult(first.result), basis=VerificationMethod(first.basis), confirmed_by=_user_out(confirmer),
        )
    elif answer is not None:
        status = "answered"
    return InterviewQuestionOut(
        question_id=question.id,
        kind=str(question.kind),
        sort_order=question.sort_order,
        question=question.question,
        criterion=CriterionOut(**question.criterion) if question.criterion else None,
        author=str(question.author),
        gap=question.gap,
        gap_ref_id=question.gap_ref_id,
        rubric_question_id=question.rubric_question_id,
        sources=question.sources or [],
        status=status,
        resolved_by=resolved_by,
        carried_from_question_id=question.carried_from_question_id,
        answer=_answer_out(session, answer, carried) if answer else None,
    )


def _users(session: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, User]:
    ids = {i for i in ids if i is not None}
    return {u.id: u for u in session.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _user_out(user: User | None) -> InterviewUserOut | None:
    return InterviewUserOut(user_id=user.id, login=user.login) if user else None


def _answer_out(session: Session, answer: InterviewAnswer, carried: bool = False) -> AnswerOut:
    author = session.get(User, answer.author_user_id) if answer.author_user_id else None
    return AnswerOut(
        answer_id=answer.id, question_id=answer.question_id, revision=answer.revision, text=answer.text,
        source=str(answer.source), author=_user_out(author), created_at=answer.created_at,
        previous_answer_id=answer.previous_answer_id, carried_over=carried,
    )


# --- Ответы -------------------------------------------------------------------------------

def _interview_or_404(session: Session, interview_id: uuid.UUID) -> Interview:
    interview = session.get(Interview, interview_id)
    if interview is None:
        raise not_found("INTERVIEW_NOT_FOUND", "Интервью не найдено", interview_id=interview_id)
    return interview


def add_answer(session: Session, interview_id: uuid.UUID, question_id: uuid.UUID, body: AnswerIn,
               user: User) -> tuple[AnswerOut, bool]:
    interview = _interview_or_404(session, interview_id)
    require_working_application(session.get(Application, interview.application_id))
    try:
        answer, created = repo.add_interview_answer(
            session, interview_id=interview.id, question_id=question_id, text=body.text,
            source=AnswerSource(body.source), expected_revision=body.expected_revision,
            request_id=body.request_id, author_user_id=user.id,
        )
    except repo.RuleConflict as error:
        session.rollback()
        raise rule_error(error) from error
    except repo.RepositoryError as error:
        session.rollback()
        raise ApiError(422, "ANSWER_REJECTED", _sentence(str(error))) from error
    session.commit()
    return _answer_out(session, answer), created


def list_answers(session: Session, interview_id: uuid.UUID, question_id: uuid.UUID) -> AnswerListOut:
    interview = _interview_or_404(session, interview_id)
    question = session.scalar(select(InterviewQuestion).where(
        InterviewQuestion.id == question_id, InterviewQuestion.interview_id == interview.id))
    if question is None:
        raise not_found("QUESTION_NOT_FOUND", "Вопрос не из этого интервью", question_id=question_id)
    return AnswerListOut(question_id=question.id,
                         items=[_answer_out(session, a) for a in repo.question_answers(session, question.id)])


# --- Подтверждение требования ------------------------------------------------------------------

def confirm_requirement(session: Session, assessment_id: uuid.UUID, requirement_id: uuid.UUID, body: ConfirmIn,
                        user: User) -> tuple[AssessmentOut, bool]:
    """confirm_formal_check по HTTP. Вернуть (новая версия оценки, создана ли): 201 / повтор 200."""
    replay = repo.find_confirmation(session, body.request_id)
    if replay is None and session.get(Assessment, assessment_id) is None:
        raise not_found("ASSESSMENT_NOT_FOUND", "Оценка не найдена", assessment_id=assessment_id)
    try:
        assessment = repo.confirm_formal_check(
            session, assessment_id=assessment_id, requirement_id=requirement_id, result=CheckResult(body.result),
            basis=VerificationMethod(body.basis), actor_user_id=user.id, comment=body.comment,
            answer_id=body.answer_id, request_id=body.request_id,
        )
    except repo.RuleConflict as error:
        session.rollback()
        raise rule_error(error) from error
    except repo.RepositoryError as error:
        session.rollback()
        raise ApiError(422, "CONFIRM_REJECTED", _sentence(str(error))) from error
    created = replay is None and assessment.confirm_request_id == body.request_id
    session.commit()
    return _assessment_out(session, assessment), created


def _assessment_out(session: Session, assessment: Assessment) -> AssessmentOut:
    candidate = session.get(Candidate, assessment.candidate_id)
    profile = session.get(RequirementProfile, assessment.profile_id)
    state = AssessmentState(AssessmentStatus.READY, assessment)
    approved = repo.get_approved_profile(session, profile.position_id, synthetic=profile.is_synthetic)
    if approved is not None and approved.id == profile.id:
        resolved = resolve_states(session, [candidate.id], approved, profile.position_id, profile.is_synthetic)
        if resolved[candidate.id].assessment is not None and resolved[candidate.id].assessment.id == assessment.id:
            state = resolved[candidate.id]
    return assessment_out(session, candidate, state)


# --- Итог телефонной встречи (wave-2-stage-1, раздел «Илья») ------------------------------------

# Допуск на расхождение часов клиента и сервера: «разговор через минуту» — ещё не ошибка ввода.
CLOCK_SKEW = timedelta(minutes=5)


def interview_out(interview: Interview) -> InterviewOut:
    return InterviewOut(
        id=interview.id, application_id=interview.application_id, kind=str(interview.kind),
        scheduled_at=interview.scheduled_at, held_at=interview.held_at, attempt_at=interview.attempt_at,
        result=str(interview.result), summary=interview.summary, interviewer_user_id=interview.interviewer_user_id,
        outcome_recorded_at=interview.outcome_recorded_at, revision=interview.revision,
    )


def list_interviews(session: Session, application_id: uuid.UUID) -> InterviewListOut:
    """Все встречи отклика, старые сначала: завершённые с итогом, прежние без итога и текущая pending."""
    application = get_application_or_404(session, application_id)
    # created_at — время транзакции: встречи, открытые в одной транзакции, равны по нему,
    # поэтому при равенстве открытая (pending) идёт после завершённых, затем по id.
    rows = session.scalars(select(Interview).where(Interview.application_id == application.id)
                           .order_by(Interview.created_at, Interview.result == InterviewResult.PENDING,
                                     Interview.id))
    return InterviewListOut(application_id=application.id, items=[interview_out(i) for i in rows])


def _same_outcome(interview: Interview, body: InterviewOutcomeIn, user: User) -> bool:
    """Повтор в точности той же команды того же актора (expected_revision не сравнивается:
    после первой записи она уже устарела, а повтор должен вернуть прежний результат)."""
    return (str(interview.result) == body.result and interview.attempt_at == body.occurred_at
            and interview.summary == body.summary and interview.interviewer_user_id == user.id)


def record_outcome(session: Session, interview_id: uuid.UUID, body: InterviewOutcomeIn, user: User) -> InterviewOut:
    """Завершить телефонную встречу: continue/stop — разговор состоялся (held_at = attempt_at = occurred_at),
    no_answer — только попытка (held_at пуст). Этап отклика, отказ и резерв не меняются.

    Строка встречи блокируется (FOR UPDATE), поэтому две параллельные команды не перезапишут один итог:
    вторая увидит завершённую встречу и получит повтор либо 409 INTERVIEW_ALREADY_COMPLETED."""
    interview = session.scalar(select(Interview).where(Interview.id == interview_id).with_for_update())
    if interview is None:
        raise not_found("INTERVIEW_NOT_FOUND", "Интервью не найдено", interview_id=interview_id)
    require_working_application(session.get(Application, interview.application_id))
    if interview.kind != InterviewKind.PHONE:
        raise ApiError(409, "UNSUPPORTED_INTERVIEW_KIND", "Итог записывается только для телефонной встречи",
                       {"kind": str(interview.kind)})
    if interview.result != InterviewResult.PENDING:
        if _same_outcome(interview, body, user):
            return interview_out(interview)
        raise ApiError(409, "INTERVIEW_ALREADY_COMPLETED", "Итог встречи уже записан: исправление — отдельная команда",
                       {"result": str(interview.result), "revision": interview.revision})
    if interview.revision != body.expected_revision:
        raise ApiError(409, "STALE_REVISION", "Встречу уже изменили: перечитайте её",
                       {"revision": interview.revision})
    now = datetime.now(UTC)
    if body.occurred_at > now + CLOCK_SKEW:
        raise ApiError(422, "INVALID_OCCURRED_AT", "Время разговора не может быть в будущем",
                       {"field": "occurred_at"})

    held = body.result != InterviewResult.NO_ANSWER
    interview.result = InterviewResult(body.result)
    interview.attempt_at = body.occurred_at
    interview.held_at = body.occurred_at if held else None
    interview.summary = body.summary
    interview.interviewer_user_id = user.id
    interview.outcome_recorded_at = now
    interview.revision += 1
    repo.write_audit(session, action=AuditAction.OTHER, entity_type="interview", entity_id=str(interview.id),
                     user_id=user.id, details={
                         "event": "interview.outcome_recorded", "application_id": str(interview.application_id),
                         "result": body.result, "occurred_at": body.occurred_at.isoformat(),
                         "held": held, "revision": interview.revision})
    session.commit()
    return interview_out(interview)
