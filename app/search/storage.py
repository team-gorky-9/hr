"""Доступ к актуальному очищенному корпусу, резерву и индексу pgvector."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, bindparam, case, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.schemas import Contour
from app.db.enums import ApplicationSource, VacancyStatus
from app.db.models.candidates import Candidate, CandidateCard, CandidateSkill, CandidateText
from app.db.models.positions import Position, Vacancy
from app.db.models.search import Embedding
from app.db.models.selection import Application, ReserveEntry, SelectionStage
from app.db.repository import active_reserve_condition, normalize_skill
from app.schemas.card import normalize_education_level
from app.search.encoder import Encoder, checked_vectors
from app.search.ranking import Document, Passage
from app.search.schemas import SearchApplication, SearchFilterMatch, SearchRequest
from app.search.text import split_chunks


@dataclass(slots=True)
class CandidateRow:
    document: Document
    card_id: UUID | None
    education_level: str | None
    in_reserve: bool


def load_candidates(session: Session, request: SearchRequest, *, today: date | None = None) -> list[CandidateRow]:
    filters = request.filters
    # Правило «резерв действует» — общее с API резерва (backend-02): repository.active_reserve_condition.
    reserve = exists().where(ReserveEntry.candidate_id == Candidate.id, active_reserve_condition(today))
    statement = (
        select(Candidate.id, Candidate.code, CandidateText.id, CandidateText.text,
               CandidateCard.id, CandidateCard.education_level, reserve.label("in_reserve"))
        .join(CandidateText, and_(CandidateText.candidate_id == Candidate.id, CandidateText.is_current))
        .outerjoin(CandidateCard, and_(CandidateCard.candidate_id == Candidate.id,
                                      CandidateCard.candidate_text_id == CandidateText.id,
                                      CandidateCard.is_current))
        .where(Candidate.is_synthetic.is_(request.contour == Contour.TRAINING))
        .order_by(Candidate.code)
    )
    if filters.in_reserve is not None:
        statement = statement.where(reserve if filters.in_reserve else ~reserve)
    skills = set(map(normalize_skill, filters.skills))
    if skills:
        found = (
            select(func.count(CandidateSkill.id))
            .where(CandidateSkill.card_id == CandidateCard.id, CandidateSkill.candidate_id == Candidate.id,
                   CandidateSkill.normalized.in_(skills))
            .scalar_subquery()
        )
        statement = statement.where(found >= (len(skills) if filters.skill_match == "all" else 1))
    if not request.query and not filters.required_terms and not filters.education_levels:
        statement = statement.limit(request.limit)
    rows = []
    for candidate_id, code, text_id, text, card_id, stored_level, in_reserve in session.execute(statement):
        level = normalize_education_level(stored_level) if stored_level else None
        if not filters.education_levels or level in filters.education_levels:
            rows.append(CandidateRow(Document(candidate_id, code, text_id, text), card_id, level, in_reserve))
    if not request.query and not filters.required_terms:
        return rows[:request.limit]
    return rows


def load_applications(session: Session, candidates: list[UUID]) -> dict[UUID, list[SearchApplication]]:
    if not candidates:
        return {}
    active = and_(
        Application.source.in_([ApplicationSource.RESPONSE, ApplicationSource.MANUAL]),
        Vacancy.status == VacancyStatus.OPEN,
        SelectionStage.is_final.is_(False),
    )
    statement = (
        select(
            Application.candidate_id,
            Application.id.label("application_id"),
            Application.source,
            Application.vacancy_id,
            Vacancy.position_id,
            Position.title.label("position_title"),
            Application.posting_title,
            Application.external_position_title,
            Application.applied_at,
            Application.current_stage_code.label("stage_code"),
            func.coalesce(active, False).label("is_active"),
        )
        .join(SelectionStage, SelectionStage.code == Application.current_stage_code)
        .outerjoin(Vacancy, Vacancy.id == Application.vacancy_id)
        .outerjoin(Position, Position.id == Vacancy.position_id)
        .where(Application.candidate_id.in_(candidates))
        .order_by(Application.candidate_id, active.desc().nulls_last(),
                  Application.applied_at.desc().nulls_last(), Application.id)
    )
    groups = defaultdict(list)
    for record in session.execute(statement).mappings():
        data = dict(record)
        groups[data.pop("candidate_id")].append(SearchApplication(**data))
    return groups


def load_filter_matches(session: Session, request: SearchRequest,
                        rows: list[CandidateRow]) -> dict[UUID, list[SearchFilterMatch]]:
    result = defaultdict(list)
    filters = request.filters
    skill_keys = set(map(normalize_skill, filters.skills))
    cards = {row.card_id: row.document.candidate_id for row in rows if row.card_id is not None}
    skills = defaultdict(list)
    if cards and skill_keys:
        statement = (
            select(CandidateSkill.card_id, CandidateSkill.candidate_id, CandidateSkill.normalized)
            .where(CandidateSkill.card_id.in_(cards), CandidateSkill.normalized.in_(skill_keys))
            .order_by(CandidateSkill.normalized)
        )
        for card_id, candidate_id, skill in session.execute(statement):
            if cards[card_id] == candidate_id:
                skills[candidate_id].append(skill)
    for row in rows:
        candidate_id = row.document.candidate_id
        if skills[candidate_id]:
            result[candidate_id].append(SearchFilterMatch(
                kind="skills", source="candidate_skills", values=skills[candidate_id]))
        if filters.education_levels and row.education_level is not None:
            result[candidate_id].append(SearchFilterMatch(
                kind="education", source="candidate_cards.education_level", values=[row.education_level]))
        if filters.in_reserve is not None:
            result[candidate_id].append(SearchFilterMatch(
                kind="reserve", source="reserve_entries", values=[row.in_reserve]))
    return result


def _current_index(model: str, dimensions: int):
    return (
        select(Embedding)
        .join(CandidateText, and_(CandidateText.id == Embedding.candidate_text_id,
                                  CandidateText.candidate_id == Embedding.candidate_id,
                                  CandidateText.is_current))
        .where(Embedding.model == model, func.vector_dims(Embedding.embedding) == dimensions,
               func.vector_norm(Embedding.embedding) > 0)
    )


def indexed_passages(session: Session, passages: dict[UUID, Passage], model: str,
                     dimensions: int) -> dict[UUID, UUID]:
    """Сопоставить фактический UUID строки индекса с UUID ожидаемого фрагмента."""
    chunks = {(passage.document.candidate_text_id, passage.chunk.kind, passage.chunk.index): passage
              for passage in passages.values()}
    text_ids = {key[0] for key in chunks}
    if not text_ids:
        return {}
    statement = (
        _current_index(model, dimensions)
        .with_only_columns(Embedding.id, Embedding.candidate_id, Embedding.candidate_text_id,
                           Embedding.chunk_kind, Embedding.chunk_index, Embedding.text,
                           Embedding.start_offset, Embedding.end_offset)
        .where(Embedding.candidate_text_id.in_(text_ids))
    )
    indexed = {}
    for row in session.execute(statement):
        expected = chunks.get((row.candidate_text_id, row.chunk_kind, row.chunk_index))
        if expected and (row.candidate_id, row.text, row.start_offset, row.end_offset) == (
                expected.document.candidate_id, expected.chunk.text, expected.chunk.start, expected.chunk.end):
            indexed[row.id] = expected.id
    return indexed


def cosine_scores(session: Session, index: dict[UUID, UUID], vector: list[float],
                  model: str, dimensions: int) -> dict[UUID, float]:
    parameter = bindparam("query_vector", value=vector, type_=Vector(dimensions))
    # CASE защищает оператор от несовместимой размерности даже при перестановке условий planner.
    similarity = case((func.vector_dims(Embedding.embedding) == dimensions,
                       1 - Embedding.embedding.cosine_distance(parameter)))
    statement = (_current_index(model, dimensions).with_only_columns(Embedding.id, similarity)
                 .where(Embedding.id.in_(index)))
    return {index[row_id]: score for row_id, score in session.execute(statement) if score is not None}


@dataclass(frozen=True, slots=True)
class IndexResult:
    action: str
    chunks: int


def index_document(session: Session, candidate_text_id: UUID, contour: Contour, encoder: Encoder) -> IndexResult:
    source = session.execute(
        select(CandidateText.candidate_id, CandidateText.text)
        .join(Candidate, Candidate.id == CandidateText.candidate_id)
        .where(CandidateText.id == candidate_text_id, CandidateText.is_current,
               Candidate.is_synthetic.is_(contour == Contour.TRAINING))
        .with_for_update(of=CandidateText)
    ).one_or_none()
    if source is None:
        return IndexResult("stale", 0)
    current = and_(Embedding.candidate_text_id == candidate_text_id, Embedding.model == encoder.model)
    rows = session.execute(select(
        Embedding.id, Embedding.candidate_id, Embedding.chunk_kind, Embedding.chunk_index,
        Embedding.text, Embedding.start_offset, Embedding.end_offset,
        func.vector_dims(Embedding.embedding), func.vector_norm(Embedding.embedding),
    ).where(current)).all()
    chunks = split_chunks(source.text)
    expected = {(source.candidate_id, chunk.kind, chunk.index, chunk.text, chunk.start,
                 chunk.end, encoder.dimensions) for chunk in chunks}
    if len(rows) == len(expected) and all(tuple(row[1:-1]) in expected and row[-1] > 0 for row in rows):
        return IndexResult("unchanged", len(chunks))
    values = checked_vectors(encoder.passages([chunk.text for chunk in chunks]), len(chunks), encoder.dimensions)
    # Удаление и бандл вставок коммитятся одной транзакцией. Блокировка текущего
    # текста сериализует индексаторы, а ключ версии не затрагивает другие модели.
    session.execute(delete(Embedding).where(current))
    if chunks:
        session.execute(insert(Embedding), [
            dict(candidate_id=source.candidate_id,
                 candidate_text_id=candidate_text_id, chunk_kind=chunk.kind, chunk_index=chunk.index,
                 text=chunk.text, start_offset=chunk.start, end_offset=chunk.end,
                 model=encoder.model, embedding=vector)
            for chunk, vector in zip(chunks, values, strict=True)
        ])
    return IndexResult("indexed", len(chunks))


def index_targets(session: Session, contour: Contour, candidate_code: str | None) -> list[UUID]:
    statement = (select(CandidateText.id).join(Candidate, Candidate.id == CandidateText.candidate_id)
                 .where(CandidateText.is_current, Candidate.is_synthetic.is_(contour == Contour.TRAINING))
                 .order_by(Candidate.code))
    if candidate_code is not None:
        statement = statement.where(Candidate.code == candidate_code)
    return list(session.scalars(statement))
