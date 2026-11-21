"""3C: подборка HR по новой публикации (wave-3-matching-stage-1) на учебном корпусе поиска."""
import uuid

from sqlalchemy import delete, func, select

from app.db import repository as repo
from app.db.models import Application, Candidate, MatchingSuggestion, ReserveEntry
from app.search.demo import load_demo
from tests.test_matching_candidates import HR, VACANCY_ID, client_for, snapshot

PATH = "/api/v1/matching/suggestions"


def counts(session):
    return (session.scalar(select(func.count()).select_from(Application)),
            session.scalar(select(func.count()).select_from(ReserveEntry)))


def by_code(body):
    return {item["candidate_code"]: item for item in body["items"]}


def test_create_read_and_new_revision(session, monkeypatch):
    load_demo(session)
    before = counts(session)
    with client_for(session, monkeypatch) as client:
        created = client.post(PATH, headers=HR, json={"vacancy": snapshot(), "limit": 3})
        assert created.status_code == 201, created.text
        first = created.json()
        assert (first["vacancy_ref"]["id"], first["vacancy_revision"], first["source_mode"]) == (VACANCY_ID, 1, "provided")
        assert first["created_by"]["login"] == "hr_demo" and first["created_at"] and first["qualification_note"]
        top = first["items"][0]
        assert (top["candidate_code"], top["source_status"]) == ("search-9015", "available")
        assert "Анализ и согласование требований к ИС" in top["evidence"]["fragment"]
        assert top["qualification_status"] == "not_evaluated"

        again = client.get(f"{PATH}/{first['id']}", headers=HR)
        assert (again.status_code, again.json()) == (200, first)

        edited = snapshot(revision=2, observed_at="2026-11-22T09:00:00+03:00",
                          search_query="функциональные требования к СЭД")
        second = client.post(PATH, headers=HR, json={"vacancy": edited, "limit": 3}).json()
        assert second["id"] != first["id"] and second["vacancy_revision"] == 2
        assert second["created_at"] > first["created_at"]
        assert second["items"][0]["candidate_code"] == "search-9001"
        # Первая подборка не изменилась.
        assert client.get(f"{PATH}/{first['id']}", headers=HR).json() == first
    assert session.scalar(select(func.count()).select_from(MatchingSuggestion)) == 2
    assert counts(session) == before  # ни откликов, ни записей резерва


def test_stored_fragment_is_not_disclosed_when_source_changes(session, monkeypatch):
    load_demo(session)
    with client_for(session, monkeypatch) as client:
        first = client.post(PATH, headers=HR, json={"vacancy": snapshot(), "limit": 3}).json()
        codes = by_code(first)
        target = session.scalar(select(Candidate).where(Candidate.code == "search-9015"))
        repo.add_candidate_text(session, target.id, text="Опыт работы\nНовая версия текста.", redaction_method="test")
        removed = session.scalar(select(Candidate).where(Candidate.code == "search-9001"))
        assert "search-9001" in codes
        session.execute(delete(Candidate).where(Candidate.id == removed.id))
        session.flush()

        reread = client.get(f"{PATH}/{first['id']}", headers=HR).json()
        items = {i["candidate_id"]: i for i in reread["items"]}
        superseded = items[str(target.id)]
        assert superseded["source_status"] == "superseded"
        assert superseded["evidence"]["fragment"] is None and superseded["evidence"]["candidate_text_id"]
        gone = items[str(removed.id)]
        assert (gone["source_status"], gone["evidence"], gone["candidate_code"]) == ("unavailable", None, None)
        stored = session.get(MatchingSuggestion, uuid.UUID(first["id"])).items
        assert all("fragment" not in (item["evidence"] or {}) for item in stored)  # текст в снимке не хранится


def test_access_and_rejections(session, monkeypatch):
    load_demo(session)
    with client_for(session, monkeypatch) as client:
        first = client.post(PATH, headers=HR, json={"vacancy": snapshot()}).json()
        assert client.get(f"{PATH}/{first['id']}", headers={"X-User-Login": "dept_demo"}).status_code == 403
        assert client.post(PATH, headers={"X-User-Login": "dept_demo"}, json={"vacancy": snapshot()}).status_code == 403
        assert client.get(f"{PATH}/{uuid.uuid4()}", headers=HR).json()["error"]["code"] == "SUGGESTION_NOT_FOUND"
        closed = client.post(PATH, headers=HR, json={"vacancy": snapshot(status="closed")})
        assert (closed.status_code, closed.json()["error"]["code"]) == (409, "VACANCY_NOT_PUBLISHED")
        working = client.post(PATH, headers=HR, json={"vacancy": snapshot(contour="working")})
        assert working.status_code == 401
    assert session.scalar(select(func.count()).select_from(MatchingSuggestion)) == 1  # отказы ничего не сохранили
