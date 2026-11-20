from datetime import date, timedelta

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.api.schemas import Contour
from app.db import repository as repo
from app.db.enums import ApplicationSource, ReserveStatus
from app.db.models import Application, Embedding, ReserveEntry
from app.db.session import get_session
from app.main import create_app
from app.schemas.card import Education
from app.search import api
from app.search.encoder import DIMENSIONS, INDEX_MODEL, EncoderUnavailable
from app.search.storage import index_document
from app.search.text import split_chunks
from tests.factories import add_card, make_candidate, vacancy


PATH = "/api/v1/search/candidates"
WORK = {"Authorization": "Bearer test-work-search"}


def unit_vector(first: bool, dimensions: int = DIMENSIONS):
    return [float(first), float(not first)] + [0.0] * (dimensions - 2)


class TestEncoder:
    __test__ = False
    model = INDEX_MODEL
    dimensions = DIMENSIONS

    def query(self, value):
        return unit_vector(True)

    def passages(self, values):
        return [unit_vector("СЭД" in value) for value in values]


def client_for(session, monkeypatch):
    monkeypatch.setattr(api, "get_local_encoder", TestEncoder)
    monkeypatch.setattr(api.settings, "hr_search_semantic_enabled", True)
    monkeypatch.setattr(api.settings, "hr_search_work_token", SecretStr("test-work-search"))
    monkeypatch.setattr(api.settings, "hr_search_dense_threshold", 0.9)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def index(session, candidate, *, contour=Contour.TRAINING, encoder=None):
    current = repo.get_current_text(session, candidate.id)
    return index_document(session, current.id, contour, encoder or TestEncoder())


def add_bad_index(session, candidate, vector, model=INDEX_MODEL):
    current = repo.get_current_text(session, candidate.id)
    chunk, = split_chunks(current.text)
    session.add(Embedding(
        candidate_id=candidate.id, candidate_text_id=current.id, chunk_kind=chunk.kind,
        chunk_index=chunk.index, text=chunk.text, start_offset=chunk.start, end_offset=chunk.end,
        model=model, embedding=vector,
    ))
    session.flush()


def test_exact_cosine_contour_modes_stale_text_and_invalid_index(session, monkeypatch):
    best = make_candidate(session, "search-a", "🧩\nОпыт работы\nНастраивала СЭД.\nНавыки\nСЭД.", is_synthetic=True)
    working = make_candidate(session, "search-work", "Обслуживал СЭД.")
    wrong_dimension = make_candidate(session, "search-dim", "Вторая операция.", is_synthetic=True)
    other_model = make_candidate(session, "search-other", "Третья операция.", is_synthetic=True)
    assert index(session, best).action == "indexed"
    assert index(session, best).action == "unchanged"
    assert index(session, working, contour=Contour.WORKING).chunks == 1
    assert index(session, working).action == "stale"
    add_bad_index(session, wrong_dimension, unit_vector(True, 2))
    add_bad_index(session, other_model, unit_vector(True), model="another-revision")

    with client_for(session, monkeypatch) as client:
        training = {"query": "архитектура процессов", "contour": "training"}
        result = client.post(PATH, json=training)
        assert result.status_code == 200
        payload = result.json()
        assert (payload["mode"], payload["semantic_status"]) == ("hybrid", "partial")
        item, = payload["items"]
        assert item["candidate_code"] == best.code and item["match_kind"] == "semantic"
        evidence = item["evidence"]
        text = client.get(f"/api/v1/candidate-texts/{evidence['candidate_text_id']}").json()["text"]
        assert text[evidence["start_offset"]:evidence["end_offset"]] == evidence["fragment"]
        assert evidence["utf16_start"] == evidence["start_offset"] + 1
        work = client.post(PATH, json={"query": "архитектура процессов"}, headers=WORK).json()
        assert [hit["candidate_code"] for hit in work["items"]] == [working.code]
        limited = client.post(PATH, json={**training, "filters": {"required_terms": ["несуществующий термин"]}}).json()
        assert limited["items"] == [] and limited["semantic_status"] == "ready"

        updated = repo.add_candidate_text(session, best.id, text="Опыт работы\nPostgreSQL репликация.",
                                          redaction_method="перечистка")
        stale_result = client.post(PATH, json=training).json()
        assert stale_result["items"] == [] and stale_result["semantic_status"] == "unavailable"
        fallback = client.post(PATH, json={**training, "query": "PostgreSQL"}).json()
        assert fallback["mode"] == "lexical"
        assert fallback["items"][0]["evidence"]["candidate_text_id"] == str(updated.id)
        assert index(session, best).chunks == 1
        assert index(session, wrong_dimension).action == "indexed"
        assert session.scalar(select(func.count(Embedding.id)).where(
            Embedding.candidate_id == wrong_dimension.id, Embedding.model == INDEX_MODEL,
        )) == 1
        repaired = client.post(PATH, json=training).json()
        assert repaired["items"] == [] and repaired["semantic_status"] == "partial"

        def broken_encoder():
            raise EncoderUnavailable("не найден файл")
        monkeypatch.setattr(api, "get_local_encoder", broken_encoder)
        outage = client.post(PATH, json={**training, "query": "PostgreSQL"}).json()
        assert (outage["mode"], outage["semantic_status"]) == ("lexical", "unavailable")
        assert outage["items"][0]["candidate_code"] == best.code


def test_structured_filters_reserve_legacy_cards_and_application_provenance(session, monkeypatch):
    selected = make_candidate(session, "search-selected", "Опыт работы\nРазработка Python, FastAPI.")
    second = make_candidate(session, "search-similar", "Разработка Python.")
    expired = make_candidate(session, "search-expired", "Разработка Python, FastAPI.")
    withdrawn = make_candidate(session, "search-withdrawn", "Разработка Python, FastAPI.")
    legacy = make_candidate(session, "search-legacy", "Автор методического пособия.")
    training = make_candidate(session, "search-edu", "Разработка Python, FastAPI.", is_synthetic=True)
    old_school = make_candidate(session, "search-oldcard", "Разработка Python, FastAPI.")
    add_card(session, selected, ["Python", "FastAPI"], education=[Education(level="высшее")])
    add_card(session, legacy, []).education_level = "Высшее образование (Бакалавр)"
    add_card(session, old_school, ["Python", "FastAPI"], education=[Education(level="высшее")])
    repo.add_candidate_text(session, old_school.id, text="Разработка Rust.", redaction_method="новая очистка")
    add_card(session, second, ["Python"])
    for row in (expired, withdrawn, training):
        add_card(session, row, ["Python", "FastAPI"])
    today = session.scalar(select(func.date(func.timezone("Europe/Moscow", func.now()))))
    repo.add_to_reserve(session, candidate_id=selected.id, competency_area="IT", valid_until=today)
    repo.add_to_reserve(session, candidate_id=expired.id, competency_area="IT", valid_until=today - timedelta(days=1))
    entry = repo.add_to_reserve(session, candidate_id=withdrawn.id, competency_area="IT")
    entry.status = ReserveStatus.WITHDRAWN
    repo.add_to_reserve(session, candidate_id=training.id, competency_area="IT")
    first = repo.create_application(session, candidate_id=selected.id, source=ApplicationSource.RESPONSE,
                                    vacancy_id=vacancy(session).id, posting_title="Архивное название")
    manual = repo.create_application(session, candidate_id=selected.id, source=ApplicationSource.MANUAL,
                                     vacancy_id=vacancy(session, "hr-consultant").id)
    history = repo.create_application(session, candidate_id=selected.id, source=ApplicationSource.HISTORY,
                                      external_position_title="Бывшая должность", applied_at=date(2026, 9, 1))
    session.flush()
    before = (session.scalar(select(func.count(Application.id))), session.scalar(select(func.count(ReserveEntry.id))))
    with client_for(session, monkeypatch) as client:
        result = client.post(PATH, headers=WORK, json={
            "filters": {"skills": [" Python ", "FASTAPI", "python"], "in_reserve": True, "education_levels": ["высшее"]}
        })
        assert result.status_code == 200
        payload = result.json()
        assert (payload["mode"], payload["semantic_status"]) == ("filters", "not_requested")
        hit, = payload["items"]
        assert hit["candidate_code"] == selected.code
        assert (hit["match_kind"], hit["score"], hit["evidence"]) == ("filters", None, None)
        assert hit["filter_matches"] == [
            {"kind": "skills", "source": "candidate_skills", "values": ["fastapi", "python"]},
            {"kind": "education", "source": "candidate_cards.education_level", "values": ["высшее"]},
            {"kind": "reserve", "source": "reserve_entries", "values": [True]},
        ]
        applications = {row["application_id"]: row for row in hit["applications"]}
        assert applications[str(first.id)]["is_active"] and applications[str(manual.id)]["is_active"]
        assert applications[str(first.id)]["posting_title"] == "Архивное название"
        assert applications[str(first.id)]["position_title"]
        assert not applications[str(history.id)]["is_active"]
        assert applications[str(history.id)]["external_position_title"] == "Бывшая должность"
        vacancy(session, "hr-consultant").status = "closed"
        manual_closed = client.post(PATH, headers=WORK, json={"filters": {"in_reserve": True}}).json()["items"][0]
        assert not next(row for row in manual_closed["applications"] if row["source"] == "manual")["is_active"]
        any_matches = client.post(PATH, headers=WORK, json={"filters": {
            "skills": ["FastAPI", "Python"], "skill_match": "any", "in_reserve": False
        }}).json()["items"]
        assert {hit["candidate_code"] for hit in any_matches} == {second.code, expired.code, withdrawn.code}
        by_education = client.post(PATH, headers=WORK, json={"limit": 1, "filters": {
            "education_levels": ["высшее"]
        }}).json()["items"]
        assert [hit["candidate_code"] for hit in by_education] == [legacy.code]
        assert by_education[0]["filter_matches"][0]["values"] == ["высшее"]
    assert before == (session.scalar(select(func.count(Application.id))), session.scalar(select(func.count(ReserveEntry.id))))


def test_required_terms_before_both_branches_and_filters_only_evidence(session, monkeypatch):
    actual = make_candidate(session, "search-law", "Опыт работы\nГотовила закупки 44‑ФЗ и ЕИС для СЭД.",
                            is_synthetic=True)
    lookalike = make_candidate(session, "search-commercial", "Опыт работы\nСнабжение сети через СЭД.",
                               is_synthetic=True)
    history = make_candidate(session, "search-history", "СЭД.\nИстория общения с кандидатом\n44-ФЗ ЕИС",
                             is_synthetic=True)
    for candidate in (actual, lookalike, history):
        index(session, candidate)
    with client_for(session, monkeypatch) as client:
        base = {"contour": "training", "filters": {"required_terms": ["44-ФЗ", "ЕИС", "44‑ФЗ"]}}
        hits = client.post(PATH, json={**base, "query": "закупка"}).json()["items"]
        hit, = hits
        assert hit["candidate_code"] == actual.code
        assert hit["match_kind"] == "hybrid"
        assert hit["matched_required_terms"] == ["44-ФЗ", "ЕИС"]
        exact, = client.post(PATH, json=base).json()["items"]
        assert exact["match_kind"] == "exact" and exact["score"] is None
        assert "44‑ФЗ" in exact["evidence"]["fragment"]
