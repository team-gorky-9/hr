"""HR correction of extracted assertions, without rewriting the original or re-extracting it."""
from sqlalchemy import select
from app.api.errors import ApiError
from app.assessment.artifacts import ArtifactStore, ProcessingArtifact
from app.assessment.facts import ExtractedFacts
from app.assessment.evidence import resolve_quote
from app.db import repository as repo
from app.db.models import Candidate


def effective_facts(store, facts):
    rows = store.session.scalars(select(ProcessingArtifact).where(
        ProcessingArtifact.scope == store.scope, ProcessingArtifact.kind == "fact_correction")
        .order_by(ProcessingArtifact.created_at.desc(), ProcessingArtifact.key))
    for row in rows:
        if row.dependencies["base_id"] == facts["id"]:
            return row.payload
    return facts


def correct_facts(session, candidate_id, expected_id, corrected, reason, actor):
    candidate = session.scalar(select(Candidate).where(Candidate.id == candidate_id).with_for_update())
    if candidate is None:
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Запись не найдена")
    scope = f"{'training' if candidate.is_synthetic else 'working'}:candidate:{candidate.id}"
    store = ArtifactStore(session, scope)
    previous = session.get(ProcessingArtifact, expected_id)
    text = repo.get_current_text(session, candidate.id)
    if previous is None or previous.kind not in ("resume_facts", "fact_correction") or previous.scope != scope or previous.payload.get("text_id") != str(text.id):
        raise ApiError(409, "FACTS_STALE", "Версия сведений недоступна или устарела")
    root = previous.dependencies.get("base_id", previous.key)
    original = session.get(ProcessingArtifact, root)
    current = effective_facts(store, original.payload)
    if current["id"] != expected_id:
        raise ApiError(409, "FACTS_STALE", "Сведения уже изменены")
    from pydantic import ValidationError
    try:
        result = ExtractedFacts.model_validate(corrected)
    except ValidationError:
        raise ApiError(422, "INVALID_FACTS", "Исправление не соответствует схеме сведений") from None
    assertions = []
    for item in result.assertions:
        found = resolve_quote(text.text, item.quote, candidate_text_id=text.id, context_before=item.context_before)
        if found is None:
            raise ApiError(422, "EVIDENCE_NOT_FOUND", "Цитата отсутствует в исходнике")
        assertions.append({**item.model_dump(), "evidence": found.evidence.model_dump(mode="json"),
                           "ambiguous_location": found.ambiguous_location})
    deps = {"base_id": root, "previous_id": expected_id, "actor_id": str(actor.id),
            "reason": reason, "correction": result.model_dump(mode="json")}
    payload = {**current, "id": store.key("fact_correction", deps), "assertions": assertions,
               "card": result.card.model_dump(mode="json"), "limitations": result.limitations,
               "confirmation": "hr_corrected_extraction", "actor_id": str(actor.id), "reason": reason}
    return store.put("fact_correction", deps, payload)
