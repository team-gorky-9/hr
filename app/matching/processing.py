"""Explicit paid processing command; existing /matching/vacancies remains read-only."""
from datetime import UTC, datetime

from sqlalchemy import inspect, select

from app.api.errors import ApiError
from app.assessment.artifacts import ArtifactStore, fingerprint
from app.assessment.facts import EvidenceClient, extract_facts, client_identity
from app.assessment.service import assess_candidate, record_llm_calls
from app.assessment.version import ALGORITHM_VERSION
from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.db import repository as repo
from app.db.models import Assessment, Candidate
from app.matching.service import match_profile, vacancies_for_candidate


def columns(row):
    return {attr.key: getattr(row, attr.key) for attr in inspect(row).mapper.column_attrs}


def profile_manifest(profile):
    return {"profile": columns(profile),
            "formal": [columns(r) for r in sorted(profile.formal_requirements, key=lambda r: r.key)],
            "competencies": [{**columns(c), "indicators": [columns(i) for i in c.indicators]}
                             for c in sorted(profile.competencies, key=lambda c: c.key)]}


def execute_processing(session, body, llm):
    from app.ai.errors import LLMError
    try:
        return process_vacancies(session, body, llm)
    except LLMError:
        # Preserve completed stages so a network retry does not repeat extraction.
        record_llm_calls(session, llm, body.candidate_id)
        session.commit()
        raise ApiError(503, "PROCESSING_UNAVAILABLE", "Обработка не завершена; сохранённые стадии можно использовать при повторе") from None


def save_run(session, candidate_id, contour, result, snapshots, source_mode):
    text = repo.get_current_text(session, candidate_id)
    if text is None:
        raise ApiError(409, "NO_CLEAN_TEXT", "Нет разрешённого очищенного текста")
    store = ArtifactStore(session, f"{contour}:candidate:{candidate_id}")
    dependencies = {"candidate_id": str(candidate_id), "text_id": str(text.id),
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "catalog": [v.model_dump(mode="json") for v in snapshots], "source_mode": source_mode}
    result["result"]["source_mode"] = source_mode
    payload = {**result, "run_id": store.key("matching_run", dependencies),
               "candidate_id": str(candidate_id), "contour": contour, "source_mode": source_mode,
               "text_id": str(text.id), "recorded_at": dependencies["recorded_at"]}
    return store.put("matching_run", dependencies, payload)


def process_vacancies(session, body, llm, *, as_of=None):
    candidate = session.scalar(select(Candidate).where(Candidate.id == body.candidate_id).with_for_update())
    if candidate is None:
        raise ApiError(404, "CANDIDATE_NOT_FOUND", "Кандидат не найден")
    if candidate.is_synthetic != (body.contour == "training"):
        raise ApiError(409, "CONTOUR_MISMATCH", "Кандидат из другого контура")
    text = repo.get_current_text(session, candidate.id)
    if text is None:
        raise ApiError(409, "NO_CLEAN_TEXT", "Нет разрешённого очищенного текста")
    as_of = as_of or datetime.now(UTC).strftime("%Y-%m")
    # Scope prevents reuse across source records/contours. Role and source access precede this command.
    store = ArtifactStore(session, f"{body.contour}:candidate:{candidate.id}")
    profiles = {}
    for vacancy in body.vacancies:
        if vacancy.contour != body.contour or vacancy.status != "published":
            continue
        profile, reason = match_profile(session, vacancy)
        if profile is not None:
            profiles[profile.id] = profile
    if not profiles:
        return {"result": vacancies_for_candidate(session, body).model_dump(mode="json"),
                "facts_id": None, "processed_profiles": [], "reused_profiles": [],
                "confirmation_review_required": []}
    facts = extract_facts(store, text, llm)
    from app.matching.corrections import effective_facts
    facts = effective_facts(store, facts)
    current_card = repo.get_current_card(session, candidate.id)
    if current_card is None or current_card.candidate_text_id != text.id or current_card.card != facts["card"]:
        from app.schemas.card import CandidateCard
        repo.add_candidate_card(session, candidate.id, CandidateCard.model_validate(facts["card"]),
                                extractor=llm.model_name("extract"), prompt_version=facts["version"],
                                candidate_text_id=text.id)
    client = EvidenceClient(llm, store, facts)
    processed, reused, review = [], [], []
    for profile in profiles.values():
        current = session.scalar(select(Assessment).where(Assessment.candidate_id == candidate.id,
                                 Assessment.profile_id == profile.id, Assessment.is_current))
        if current is not None and current.base_assessment_id is not None:
            # A model run must never silently replace HR's confirmed assessment.
            review.append(str(profile.id))
            continue
        dependencies = {"facts_id": facts["id"], "profile": fingerprint(profile_manifest(profile)),
                        "as_of": as_of, "algorithm": ALGORITHM_VERSION,
                        "prompt": ASSESS_PROMPT_VERSION, "provider": client_identity(llm)}
        cached = store.get("profile_assessment", dependencies)
        if cached is not None and current is not None and str(current.id) == cached["assessment_id"]:
            reused.append(str(profile.id))
            continue
        assessment_id = assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id,
            llm=client, mode="technical" if candidate.is_synthetic else "operational", as_of=as_of)
        store.put("profile_assessment", dependencies, {"assessment_id": str(assessment_id)})
        processed.append(str(profile.id))
    record_llm_calls(session, llm, candidate.id)
    return {"result": vacancies_for_candidate(session, body).model_dump(mode="json"),
            "facts_id": facts["id"], "processed_profiles": processed,
            "reused_profiles": reused, "confirmation_review_required": review}
