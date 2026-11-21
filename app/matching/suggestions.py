"""3C: сохранённая подборка HR по новой публикации.

Пример. После публикации учебной вакансии «Аналитик ИС» ред. 1 экран вызывает
POST /matching/suggestions с тем же входом, что 3A. Сервис выполняет тот же поиск и статус оценки
(candidates_for_vacancy) и сохраняет датированный снимок: кто и когда рассчитал, по какой редакции
вакансии и запросу, какие записи найдены и где цитата (candidate_text_id + границы). GET по id
перечитывает снимок. Фрагмент берётся из действующего текста кандидата: если текст заменён новой
версией или удалён, фрагмент не отдаётся, хотя факт расчёта и идентификаторы остаются. После правки
вакансии (ред. 2) новый вызов даёт вторую подборку, первая сохраняется.
Ни отклик, ни приглашение, ни запись резерва, ни право на контакт подборка не создаёт."""
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.assessment.verification import utf16_offsets
from app.db.models import Candidate, CandidateText, MatchingSuggestion, User
from app.matching.schemas import (
    CandidatesForVacancyIn,
    SuggestionEvidence,
    SuggestionItem,
    SuggestionOut,
    SuggestionUser,
)
from app.matching.service import candidates_for_vacancy
from app.search.schemas import SearchRequest, SearchResponse

QUALIFICATION_NOTE = (
    "Подборка — результат поиска на дату расчёта по указанной редакции вакансии. Формальный статус взят "
    "из сохранённой оценки по точному профилю; not_evaluated не означает допуск. Подборка не создаёт "
    "отклик, приглашение, запись резерва и не даёт права на контакт. Новый расчёт — новый вызов POST."
)


def _stored_item(item) -> dict:
    """Только разрешённая выдача и ссылка на версию источника, без текста фрагмента."""
    evidence = item.evidence
    return {
        "candidate_id": str(item.candidate_id), "candidate_code": item.candidate_code, "score": item.score,
        "match_kind": item.match_kind, "matched_required_terms": item.matched_required_terms,
        "evidence": None if evidence is None else {
            "candidate_text_id": str(evidence.candidate_text_id), "chunk_kind": str(evidence.chunk_kind),
            "start_offset": evidence.start_offset, "end_offset": evidence.end_offset},
        "qualification_status": item.qualification_status, "qualification_reason": item.qualification_reason,
        "assessment_id": str(item.assessment_id) if item.assessment_id else None,
    }


def create_suggestion(session: Session, body: CandidatesForVacancyIn, user: User,
                      search: Callable[[Session, SearchRequest], SearchResponse]) -> SuggestionOut:
    result = candidates_for_vacancy(session, body, search)
    vacancy = body.vacancy
    row = MatchingSuggestion(
        id=uuid.uuid4(), vacancy_system=vacancy.ref.system, vacancy_id=vacancy.ref.id,
        vacancy_revision=vacancy.revision,
        vacancy=vacancy.model_dump(mode="json", exclude={"description", "search_query"}),
        contour=str(vacancy.contour), source_mode=result.source_mode, search_query=vacancy.search_query,
        filters=body.filters.model_dump(mode="json"), result_limit=body.limit, mode=result.mode,
        semantic_status=result.semantic_status, items=[_stored_item(i) for i in result.items],
        created_by_user_id=user.id, created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)  # ответ POST и GET читают одно сохранённое значение (та же зона у created_at)
    return suggestion_out(session, row)


def get_suggestion(session: Session, suggestion_id: uuid.UUID) -> MatchingSuggestion:
    row = session.get(MatchingSuggestion, suggestion_id)
    if row is None:
        raise ApiError(404, "SUGGESTION_NOT_FOUND", "Подборка не найдена", {"suggestion_id": str(suggestion_id)})
    return row


def _source(session: Session, contour: str, item: dict) -> tuple[str, SuggestionEvidence | None, str | None]:
    """Проверка источника при чтении: (source_status, evidence, candidate_code)."""
    candidate = session.get(Candidate, uuid.UUID(item["candidate_id"]))
    if candidate is None or candidate.is_synthetic != (contour == "training"):
        return "unavailable", None, None
    stored = item["evidence"]
    if stored is None:
        return "available", None, candidate.code
    text = session.get(CandidateText, uuid.UUID(stored["candidate_text_id"]))
    hidden = SuggestionEvidence(**stored, fragment=None, utf16_start=None, utf16_end=None)
    if text is None or text.candidate_id != candidate.id:
        return "unavailable", hidden, candidate.code
    if not text.is_current:
        return "superseded", hidden, candidate.code
    start, end = stored["start_offset"], stored["end_offset"]
    utf16_start, utf16_end = utf16_offsets(text.text, start, end)
    return "available", SuggestionEvidence(**stored, fragment=text.text[start:end],
                                           utf16_start=utf16_start, utf16_end=utf16_end), candidate.code


def suggestion_out(session: Session, row: MatchingSuggestion) -> SuggestionOut:
    items = []
    for item in row.items:
        status, evidence, code = _source(session, row.contour, item)
        items.append(SuggestionItem(
            candidate_id=item["candidate_id"], candidate_code=code, score=item["score"],
            match_kind=item["match_kind"], evidence=evidence, source_status=status,
            matched_required_terms=item["matched_required_terms"],
            qualification_status=item["qualification_status"], qualification_reason=item["qualification_reason"],
            assessment_id=item["assessment_id"]))
    author = session.get(User, row.created_by_user_id) if row.created_by_user_id else None
    return SuggestionOut(
        id=row.id, vacancy_ref=row.vacancy["ref"], vacancy_revision=row.vacancy_revision,
        vacancy_title=row.vacancy["title"], observed_at=row.vacancy["observed_at"], created_at=row.created_at,
        created_by=SuggestionUser(user_id=author.id, login=author.login) if author else None,
        contour=row.contour, source_mode=row.source_mode, search_query=row.search_query, mode=row.mode,
        semantic_status=row.semantic_status, items=items, qualification_note=QUALIFICATION_NOTE)
