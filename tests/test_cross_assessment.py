"""Кросс-оценка (ai-02): один человек × утверждённые профили контура.

Примеры постановки ai-02: одна карточка и две оценки; повтор пропускает актуальные пары; новая
версия текста делает обе оценки устаревшими; сбой одной пары не ломает другую; отклики не создаются."""
import copy
import re
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import FakeLLMClient, LLMUnavailableError
from app.assessment.__main__ import run_one
from app.assessment.cross import Pair, cross_assessments, run_cross_batch, select_pairs
from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load
from app.db import repository as repo
from app.db.enums import ApplicationSource, Channel, DocumentKind, FileFormat
from app.db.models import Application, Assessment, CandidateCard, Position, Vacancy
from tests.factories import approve

FIXTURE = load(FIXTURES_DIR / "py-9001.json")
BASE = "Написал API-тесты для сервиса заявок."
AS_OF = "2026-11"


def second_fixture():
    """Тот же учебный профиль на другой должности, компетенция с другим названием."""
    fixture = copy.deepcopy(FIXTURE)
    fixture["profile"]["position_code"] = "hr-consultant"
    fixture["profile"]["competencies"][0]["name"] = "Работа с кадровыми документами"
    return fixture


@pytest.fixture
def setup(session):
    python = create_fixture_profile(session, FIXTURE)
    hr = create_fixture_profile(session, second_fixture())
    approve(session, python)
    approve(session, hr)
    document, _ = repo.add_source_document(session, kind=DocumentKind.RESUME, channel=Channel.HH_RU,
                                           file_format=FileFormat.TXT, original_path="Синтетика/x-1.txt",
                                           raw_text="x-1\n" + BASE)
    candidate = repo.create_candidate(session, code="x-1", source_document_id=document.id, redacted_text=BASE,
                                      redaction_method="test", is_synthetic=True)
    vacancy = session.scalar(select(Vacancy).join(Position).where(Position.code == "python-dev"))
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=vacancy.id)
    session.flush()
    return candidate, application, python, hr


def factory(session):
    """Сессии run_one видят данные теста: та же связь, точки сохранения вместо коммитов."""
    @contextmanager
    def make():
        db = Session(bind=session.connection(), join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
    return make


def responder(fail_on=None, calls=None):
    def respond(role, schema, system, user):
        if calls is not None:
            calls.append(schema)
        if fail_on and fail_on in user:
            return LLMUnavailableError("таймаут")
        if schema == "CandidateCard":
            return {"missing": ["длительность коммерческого опыта"]}
        if schema == "FormalExtraction":
            return {}
        keys = re.findall(r'"indicator_key": "([^"]+)"', user)
        return {"indicators": [{"indicator_key": k, "status": "confirmed", "quote": BASE} for k in keys]}
    return respond


def batch(session, llm_factory, **kw):
    pairs, _ = select_pairs(session, technical=True, candidate_codes=["x-1"])
    return pairs, run_cross_batch(factory(session), pairs, run_one=run_one, llm_factory=llm_factory,
                                  technical=True, as_of=AS_OF, **kw)


def count(session, model, **where):
    return session.scalar(select(func.count()).select_from(model).filter_by(**where))


def test_one_card_two_assessments_and_no_new_applications(session, setup):
    candidate, application, _, _ = setup
    applications_before = set(session.scalars(select(Application.id)))
    calls = []
    pairs, report = batch(session, lambda: FakeLLMClient(responder(calls=calls)))

    purposes = {p.position_code: (p.purpose, p.application_id) for p in pairs}
    assert purposes["python-dev"] == ("primary", application.id)
    assert purposes["hr-consultant"] == ("comparison", None)
    assert report["people"] == 1 and report["pairs"] == 2 and sum(report["counts"].values()) == 2
    assert calls.count("CandidateCard") == 1                       # карточка — один раз
    assert count(session, CandidateCard, candidate_id=candidate.id) == 1
    assert count(session, Assessment, candidate_id=candidate.id, is_current=True) == 2
    assert set(session.scalars(select(Application.id))) == applications_before


def test_repeat_with_skip_existing_does_not_call_model(session, setup):
    batch(session, lambda: FakeLLMClient(responder()))
    _, report = batch(session, lambda: FakeLLMClient(lambda *a: pytest.fail("модель не должна вызываться")),
                      skip_existing=True)
    assert report["counts"] == {"skipped_current": 2}


def test_new_text_version_makes_both_stale(session, setup):
    candidate, *_ = setup
    batch(session, lambda: FakeLLMClient(responder()))
    assert {i["assessment_status"] for i in cross_assessments(session, candidate.id)["items"]} == {"ready"}
    repo.add_candidate_text(session, candidate.id, text=BASE + " Обновлено.", redaction_method="test")
    session.flush()
    items = cross_assessments(session, candidate.id)["items"]
    assert {(i["assessment_status"], i["stale_reason"]) for i in items} == {("stale", "text_changed")}


def test_failure_of_one_pair_keeps_the_other_and_retry_completes(session, setup):
    candidate, *_ = setup
    _, report = batch(session, lambda: FakeLLMClient(responder(fail_on="Работа с кадровыми документами")))
    assert report["counts"] == {"assessed": 1, "error": 1}
    assert count(session, Assessment, candidate_id=candidate.id, is_current=True) == 1
    _, retry = batch(session, lambda: FakeLLMClient(responder()), skip_existing=True)
    assert retry["counts"] == {"skipped_current": 1, "assessed": 1}
    assert count(session, Assessment, candidate_id=candidate.id, is_current=True) == 2


def test_cross_assessments_payload(session, setup):
    candidate, application, _, _ = setup
    batch(session, lambda: FakeLLMClient(responder()))
    payload = cross_assessments(session, candidate.id, application_id=application.id)
    assert payload["context_application_id"] == str(application.id) and payload["is_training"]
    assert [a["application_id"] for a in payload["applications"]] == [str(application.id)]
    by_position = {i["position_code"]: i for i in payload["items"]}
    assert by_position["python-dev"]["is_source_position"] and not by_position["hr-consultant"]["is_source_position"]
    item = by_position["hr-consultant"]["assessment"]
    assert item["formal_result"] == "unknown" and item["gaps"]
    evidence = item["competencies"][0]["evidence"][0]
    assert evidence["quote"] == BASE and (evidence["utf16_start"], evidence["utf16_end"]) == (0, len(BASE))


def test_no_approved_profiles_gives_empty_reason(session):
    document, _ = repo.add_source_document(session, kind=DocumentKind.RESUME, channel=Channel.HH_RU,
                                           file_format=FileFormat.TXT, original_path="Синтетика/x-2.txt",
                                           raw_text="x-2\n" + BASE)
    candidate = repo.create_candidate(session, code="x-2", source_document_id=document.id, redacted_text=BASE,
                                      redaction_method="test", is_synthetic=True)
    payload = cross_assessments(session, candidate.id)
    assert payload["items"] == [] and payload["empty_reason"] == "no_approved_profiles"


def test_concurrent_write_is_retried_once_and_counts_add_up():
    """Конфликт уникального индекса текущей оценки: повтор берёт готовую оценку. Без базы."""
    import uuid

    pairs = [Pair(uuid.uuid4(), f"c{n}", uuid.uuid4(), "python-dev", "comparison", None) for n in range(3)]
    attempts: dict[str, int] = {}

    def fake_run_one(factory_, llm, *, candidate_code, **kw):
        attempts[candidate_code] = attempts.get(candidate_code, 0) + 1
        if candidate_code == "c1" and attempts[candidate_code] == 1:
            raise IntegrityError("insert", {}, Exception("uq_assessments_current"))
        return {"status": "ok", "reused": candidate_code == "c1", "assessment_id": "a", "formal_result": "met"}

    report = run_cross_batch(None, pairs, run_one=fake_run_one, llm_factory=lambda: None, technical=True,
                             as_of=AS_OF, workers=3)
    assert report["counts"] == {"assessed": 2, "reused": 1} and attempts["c1"] == 2
