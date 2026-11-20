"""Общий поисковый конвейер для HTTP."""
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.assessment.verification import utf16_offsets
from app.search.encoder import DIMENSIONS, INDEX_MODEL, Encoder, EncoderUnavailable, checked_vectors
from app.search.ranking import Passage, Prepared, Ranked, bm25, fuse, prepare, rank_branch
from app.search.schemas import SearchEvidence, SearchHit, SearchMode, SearchRequest, SearchResponse, SemanticStatus
from app.search.storage import cosine_scores, indexed_passages, load_applications, load_candidates, load_filter_matches

logger = logging.getLogger(__name__)
EncoderFactory = Callable[[], Encoder]


def evidence_of(passage: Passage | None) -> SearchEvidence | None:
    if passage is None:
        return None
    chunk = passage.chunk
    doc = passage.document
    utf16_start, utf16_end = utf16_offsets(doc.text, chunk.start, chunk.end)
    return SearchEvidence(candidate_text_id=doc.candidate_text_id, chunk_kind=chunk.kind, fragment=chunk.text,
                          start_offset=chunk.start, end_offset=chunk.end,
                          utf16_start=utf16_start, utf16_end=utf16_end)


def _semantic_candidates(session: Session, query: str, prepared: Prepared,
                         encoder_factory: EncoderFactory | None, threshold: float,
                         model: str, dimensions: int) -> tuple[list[Ranked], SemanticStatus]:
    if encoder_factory is None:
        return [], "unavailable"
    if not prepared.passages:
        return [], "ready"
    indexed = indexed_passages(session, prepared.passages, model, dimensions)
    if not indexed:
        return [], "unavailable"
    try:
        encoder = encoder_factory()
        if (encoder.model, encoder.dimensions) != (model, dimensions):
            raise EncoderUnavailable("Модель запроса не совпадает с моделью индекса")
        vector = checked_vectors([encoder.query(query)], 1, dimensions)[0]
    except EncoderUnavailable:
        # В сообщении нет поисковой строки, фрагментов или исходного исключения токенизатора.
        logger.warning("Плотный поиск недоступен, выполнена лексическая ветка")
        return [], "unavailable"
    scores = cosine_scores(session, indexed, vector, model, dimensions)
    status = "ready" if len(indexed) == len(prepared.passages) else "partial"
    return rank_branch(prepared, scores, "semantic", threshold), status


def search_candidates(session: Session, request: SearchRequest, *,
                      encoder_factory: EncoderFactory | None, threshold: float,
                      model: str = INDEX_MODEL, dimensions: int = DIMENSIONS) -> SearchResponse:
    rows = load_candidates(session, request)
    passage_by_candidate = {}
    if request.query:
        prepared = prepare([row.document for row in rows], request.query, request.filters.required_terms)
        semantic, status = _semantic_candidates(
            session, request.query, prepared, encoder_factory, threshold, model, dimensions)
        mode: SearchMode = "lexical" if status == "unavailable" else "hybrid"
        ranked = fuse(bm25(prepared), semantic)[:request.limit]
        by_id = {row.document.candidate_id: row for row in rows}
        rows = [by_id[hit.passage.document.candidate_id] for hit in ranked]
        passage_by_candidate = {hit.passage.document.candidate_id: hit for hit in ranked}
    else:
        mode, status = "filters", "not_requested"
        if request.filters.required_terms:
            prepared = prepare([row.document for row in rows], "", request.filters.required_terms)
            rows = [row for row in rows if row.document.candidate_id in prepared.candidates][:request.limit]
            passage_by_candidate = {
                candidate_id: Ranked(passage, 0, "exact")
                for candidate_id, passage in prepared.exact_evidence.items()
            }
    applications = load_applications(session, [row.document.candidate_id for row in rows])
    matches = load_filter_matches(session, request, rows)
    items = []
    for row in rows:
        candidate_id = row.document.candidate_id
        hit = passage_by_candidate.get(candidate_id)
        items.append(SearchHit(
            candidate_id=candidate_id,
            candidate_code=row.document.code,
            score=hit.score if request.query and hit else None,
            match_kind=hit.kind if hit else "filters",
            evidence=evidence_of(hit.passage if hit else None),
            matched_required_terms=request.filters.required_terms,
            filter_matches=matches.get(candidate_id, []),
            in_reserve=row.in_reserve,
            applications=applications.get(candidate_id, []),
        ))
    return SearchResponse(contour=request.contour, mode=mode, semantic_status=status, items=items)
