"""HTTP API Этапа 1 (контракт api.md v0.2) на настоящей PostgreSQL.

Данные создаются настоящими функциями доступа (repository) в транзакции теста, API
получает ту же сессию через подмену зависимости get_session. Сценарии py-9001 берутся
из общего контрольного набора fixtures/assessment/py-9001.json — того же, что у оценки.
"""
from datetime import date
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.services import utf16_offset
from app.assessment.version import ALGORITHM_VERSION
from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.db import repository as repo
from app.db.enums import ApplicationSource, CheckResult, VerificationMethod
from app.db.models import Candidate, CandidatePii, RequirementProfile
from app.db.session import get_session
from app.main import create_app
from app.schemas.assessment import AlternativeResultIn, CompetencyScoreIn, FormalCheckIn
from app.schemas.card import CandidateCard, Evidence
from tests import factories as f
from tests.posting_helpers import confirm_response, posting_registry  # noqa: F401 (fixture)
from tests.test_assessment_fixtures_db import FIXTURE, _load_profile, _load_texts, _remap

CASES = {case["id"]: case for case in FIXTURE["cases"]}

# Синтетические ПДн: ни одно из этих значений не должно появиться ни в одном ответе API.
PII = {
    "full_name": "Иванов Тест Тестович",
    "phone": "+7 999 000-00-01",
    "email": "test.ivanov@example.com",
    "link": "https://github.com/test-ivanov",
    "city": "Тестоград",
}
RAW_MARKER = "RAW-ONLY-MARKER"  # есть только в source_documents.raw_text


@pytest.fixture
def client(session: Session, posting_registry) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


# --- Сборка сценариев ----------------------------------------------------------

def _add_pii(session: Session, candidate_id: uuid.UUID) -> None:
    session.add(CandidatePii(candidate_id=candidate_id, full_name=PII["full_name"], phone=PII["phone"],
                             email=PII["email"], city=PII["city"], links=[PII["link"]]))
    session.flush()


def build_case(session: Session, case_id: str, *, approve: bool = True, assess: bool = True,
               confirm: bool = True) -> dict:
    """Учебный py-9001 из набора: кандидат, отклик на python-dev, учебный профиль, карточка, оценка."""
    case = CASES[case_id]
    ids = _load_texts(session, case)
    profile_id, profile_ids = _load_profile(session)
    ids |= profile_ids
    candidate_id = ids["candidate"]
    _add_pii(session, candidate_id)
    application = repo.create_application(
        session, candidate_id=candidate_id, source=ApplicationSource.RESPONSE, vacancy_id=f.vacancy(session).id
    )
    if confirm:
        confirm_response(session, application, "python-dev")
    if approve:
        f.approve(session, session.get(RequirementProfile, profile_id))
    result = {"ids": ids, "candidate_id": candidate_id, "application_id": application.id, "profile_id": profile_id}
    if assess:
        assessed_text_id = ids[FIXTURE["texts"][case["assessed_text"]]["id"]]
        card = repo.add_candidate_card(session, candidate_id, CandidateCard.model_validate(case["card"]),
                                       extractor="fixture", candidate_text_id=assessed_text_id)
        checks = [FormalCheckIn.model_validate(_remap(i["check"], ids)) for i in case["assessment"]["formal_checks"]]
        scores = [CompetencyScoreIn.model_validate(_remap(i["score"], ids))
                  for i in case["assessment"]["competency_scores"]]
        assessment = repo.save_assessment(session, candidate_id=candidate_id, profile_id=profile_id, card_id=card.id,
                                          model="fixture", formal_checks=checks, competency_scores=scores,
                                          algorithm_version=ALGORITHM_VERSION, prompt_version=ASSESS_PROMPT_VERSION)
        result |= {"assessment_id": assessment.id, "text_id": assessed_text_id}
    return result


def training_list(client: TestClient, **params) -> dict:
    vacancy_id = _python_vacancy_id(client)
    response = client.get(f"/api/v1/vacancies/{vacancy_id}/applications", params={"contour": "training", **params})
    assert response.status_code == 200, response.text
    return response.json()


def _python_vacancy_id(client: TestClient) -> str:
    items = client.get("/api/v1/vacancies").json()["items"]
    return next(v["vacancy_id"] for v in items if v["position_code"] == "python-dev")


def detail(client: TestClient, application_id) -> dict:
    response = client.get(f"/api/v1/applications/{application_id}")
    assert response.status_code == 200, response.text
    return response.json()


# --- Каркас --------------------------------------------------------------------

def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok", "db": "ok"}


def test_health_reports_unavailable_database():
    dead = create_engine("postgresql+psycopg://hr:hr@127.0.0.1:1/hr_test", connect_args={"connect_timeout": 1})
    app = create_app()

    def broken_session():
        with Session(dead) as s:
            yield s

    app.dependency_overrides[get_session] = broken_session
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "error"}


STAGE_1_ROUTES = {
    "/api/v1/health",
    "/api/v1/vacancies",
    "/api/v1/vacancies/{vacancy_id}/applications",
    "/api/v1/applications/{application_id}",
    "/api/v1/applications/{application_id}/comparison",
    "/api/v1/candidate-texts/{candidate_text_id}",
    "/api/v1/applications/{application_id}/posting-resolution",
    "/api/v1/posting-snapshots",
    "/api/v1/posting-snapshots/{snapshot_id}",
}

# Маршруты backend-02 (api.md раздел 3); состав и методы проверяет tests/test_api_workflow.py.
STAGE_2_ROUTES = {
    "/api/v1/references/stages",
    "/api/v1/references/rejection-reasons",
    "/api/v1/applications/{application_id}/stage",
    "/api/v1/applications/{application_id}/history",
    "/api/v1/candidates/{candidate_id}/cross-assessments",
    "/api/v1/reserve",
    "/api/v1/reserve/{reserve_id}/withdraw",
    "/api/v1/positions/{position_id}/reserve",
    "/api/v1/analytics/funnel",
}
# Гайд интервью, ответы и подтверждение требования (interview.md v0.4, interview-01).
INTERVIEW_ROUTES = {
    "/api/v1/applications/{application_id}/interview-guide",
    "/api/v1/interviews/{interview_id}/questions/{question_id}/answers",
    "/api/v1/assessments/{assessment_id}/formal-checks/{requirement_id}/confirm",
    # wave-2-stage-1: итог телефонной встречи и чтение встреч отклика.
    "/api/v1/applications/{application_id}/interviews",
    "/api/v1/interviews/{interview_id}/outcome",
    # wave-3-matching-stage-1: люди под выбранную вакансию (3A).
    "/api/v1/matching/candidates",
    "/api/v1/matching/vacancies",  # 3B: вакансии по присланному резюме
    "/api/v1/matching/suggestions",  # 3C: сохранённая подборка после публикации
    "/api/v1/matching/suggestions/{suggestion_id}",
    "/api/v1/management/overview",  # wave-4 4A: текущая работа и факты интервью
    "/api/v1/management/annual-reports",  # wave-4 4B: годовой выпуск из фактов legacy-hr
    "/api/v1/management/annual-reports/{snapshot_id}",
    "/api/v1/management/annual-reports/{snapshot_id}/xlsx",
    "/api/v1/management/plans",  # wave-4 4C: плановый снимок потребностей
    "/api/v1/management/plans/{plan_id}",
    "/api/v1/management/plans/{plan_id}/summary",
}

WORKFLOW_01_ROUTES = {
    "/api/v1/applications/{application_id}/handoff-summary",
    "/api/v1/applications/{application_id}/handoffs",
    "/api/v1/applications/{application_id}/handoffs/{attempt_id}/deadline",
    "/api/v1/handoffs",
    "/api/v1/handoffs/{attempt_id}",
    "/api/v1/applications/{application_id}/feedback",
}


def test_openapi_has_all_stage_1_routes(client):
    """Маршруты чтения этапа 1 на месте, а лишних нет: кроме них — маршруты backend-02,
    workflow-01, поиск и годовой отчёт (hr#16). Новый модуль маршрутов добавляет сюда свой префикс."""
    paths = set(client.get("/openapi.json").json()["paths"])
    assert STAGE_1_ROUTES <= paths
    extra = paths - STAGE_1_ROUTES - STAGE_2_ROUTES - WORKFLOW_01_ROUTES - INTERVIEW_ROUTES
    assert {p for p in extra if not p.startswith("/api/v1/reports/annual")} == {"/api/v1/search/candidates"}


def test_cors_allows_vite_dev_server(client):
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- Статусы оценки py-9001 ----------------------------------------------------

@pytest.mark.parametrize("case_id", ["C1-unknown", "C2-met", "C3-not-met", "C4-not-met-strong-competency"])
def test_py9001_ready_assessment_matches_fixture(session, client, case_id):
    built = build_case(session, case_id)
    expected = CASES[case_id]["expect"]["formal_result"]

    [item] = training_list(client)["items"]
    assert item["candidate_code"] == "py-9001"
    assert item["assessment_status"] == "ready"
    assert item["formal_result"] == expected
    assert item["is_training"] is True

    body = detail(client, built["application_id"])
    assert body["assessment_status"] == "ready"
    assessment = body["assessment"]
    assert assessment["formal_result"] == expected
    assert assessment["is_stale"] is False and assessment["stale_reason"] is None
    assert assessment["is_training"] is True
    assert assessment["profile_status"] == "approved"
    [check] = assessment["formal_checks"]
    assert check["check_stage"] == "screening" and check["basis"] == "resume"
    assert check["source_quote"] == FIXTURE["profile"]["synthetic_role"]  # строка команды → обоснование


def test_py9001_quote_offsets_for_browser_match_fixture_ui(session, client):
    """C5: эмодзи перед цитатой — границы в кодовых точках и UTF-16 различаются."""
    built = build_case(session, "C5-non-bmp")
    [expected] = CASES["C5-non-bmp"]["ui"]["evidence"]

    [score] = detail(client, built["application_id"])["assessment"]["competency_scores"]
    [evidence] = score["evidence"]
    assert (evidence["start"], evidence["end"]) == (expected["start"], expected["end"])
    assert (evidence["utf16_start"], evidence["utf16_end"]) == (expected["utf16_start"], expected["utf16_end"])
    assert evidence["utf16_start"] == evidence["start"] + 1

    text = client.get(f"/api/v1/candidate-texts/{evidence['candidate_text_id']}").json()
    assert text["char_length"] + 1 == text["utf16_length"]
    # Срез в JS по utf16-границам — это срез UTF-16 строки.
    utf16 = text["text"].encode("utf-16-le")
    assert utf16[evidence["utf16_start"] * 2:evidence["utf16_end"] * 2].decode("utf-16-le") == evidence["quote"]


def test_utf16_offset_counts_surrogate_pairs():
    assert utf16_offset("🚀 Написал API-тесты для сервиса заявок.", 2) == 3
    assert utf16_offset("abc", 3) == 3


def test_not_assessed_is_not_unknown(session, client):
    built = build_case(session, "C1-unknown", assess=False)
    [item] = training_list(client)["items"]
    assert item["assessment_status"] == "not_assessed"
    assert item["formal_result"] is None and item["overall_score"] is None
    body = detail(client, built["application_id"])
    assert body["assessment_status"] == "not_assessed" and body["assessment"] is None


def test_unproven_original_does_not_inherit_imported_python_profile(session, client):
    built = build_case(session, "C1-unknown", confirm=False)
    [item] = training_list(client)["items"]
    assert item["assessment_status"] == "mapping_required"
    assert item["formal_result"] is None
    body = detail(client, built["application_id"])
    assert body["assessment_status"] == "mapping_required" and body["assessment"] is None
    resolution = client.get(f"/api/v1/applications/{built['application_id']}/posting-resolution").json()
    assert resolution["ready"] is False and resolution["mapping"]["decision_state"] == "needs_review"
    assert resolution["profile_id"] is None


def test_no_approved_profile_when_profile_is_draft(session, client):
    """N7-подобный случай: профиль-черновик не действует, даже если по нему есть оценка."""
    built = build_case(session, "C1-unknown", approve=False)
    [item] = training_list(client)["items"]
    assert item["assessment_status"] == "no_approved_profile"
    assert item["formal_result"] is None
    body = detail(client, built["application_id"])
    assert body["assessment_status"] == "no_approved_profile" and body["assessment"] is None
    vacancy = next(v for v in client.get("/api/v1/vacancies", params={"contour": "training"}).json()["items"]
                   if v["position_code"] == "python-dev")
    assert vacancy["approved_profile_id"] is None


def test_stale_when_text_changed(session, client):
    built = build_case(session, "C1-unknown")
    repo.add_candidate_text(session, built["candidate_id"], text="Новая очистка. Написал API-тесты.",
                            redaction_method="test-v2")
    [item] = training_list(client)["items"]
    assert item["assessment_status"] == "stale"
    assert item["formal_result"] == "unknown"  # прежний результат виден с пометкой
    assessment = detail(client, built["application_id"])["assessment"]
    assert assessment["is_stale"] is True and assessment["stale_reason"] == "text_changed"
    # Цитаты старой оценки по-прежнему указывают на свою (прежнюю) версию текста.
    [evidence] = assessment["competency_scores"][0]["evidence"]
    assert evidence["candidate_text_id"] == str(built["text_id"])


def test_stale_when_approved_profile_changed(session, client):
    built = build_case(session, "C1-unknown")
    new_profile_id, _ = _load_profile(session)
    f.approve(session, session.get(RequirementProfile, new_profile_id))  # v1 уходит в архив

    [item] = training_list(client)["items"]
    assert item["assessment_status"] == "stale"
    assessment = detail(client, built["application_id"])["assessment"]
    assert assessment["stale_reason"] == "profile_changed"
    assert assessment["profile_id"] == str(built["profile_id"]) and assessment["profile_status"] == "archived"


# --- Контуры -------------------------------------------------------------------

def test_training_candidate_is_hidden_from_working_contour(session, client):
    build_case(session, "C1-unknown")
    real = f.make_candidate(session, "py-0001")
    response = repo.create_application(session, candidate_id=real.id, source=ApplicationSource.RESPONSE,
                                       vacancy_id=f.vacancy(session).id)
    confirm_response(session, response, "python-dev")
    vacancy_id = _python_vacancy_id(client)

    working = client.get(f"/api/v1/vacancies/{vacancy_id}/applications").json()
    assert [i["candidate_code"] for i in working["items"]] == ["py-0001"]
    # Утверждён только учебный профиль: в рабочем контуре профиля нет.
    assert working["items"][0]["assessment_status"] == "no_approved_profile"
    assert working["items"][0]["is_training"] is False
    assert [i["candidate_code"] for i in training_list(client)["items"]] == ["py-9001"]

    def python_row(contour):
        items = client.get("/api/v1/vacancies", params={"contour": contour}).json()["items"]
        return next(v for v in items if v["position_code"] == "python-dev")

    assert python_row("working")["applications_count"] == 1
    assert python_row("working")["approved_profile_id"] is None
    assert python_row("training")["applications_count"] == 1
    assert python_row("training")["approved_profile_is_training"] is True


def test_real_candidate_formal_check_fields(session, client):
    """Рабочий контур: альтернативы, предварительный результат и подтверждение документом."""
    text = "Высшее образование, Юриспруденция, 2018."
    candidate = f.make_candidate(session, "hr-0001", text=text)
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=f.vacancy(session, "hr-consultant").id)
    profile = f.approve(session, f.make_profile(session))
    card = f.add_card(session, candidate, skills=[])
    text_id = repo.get_current_text(session, candidate.id).id
    level = next(r for r in profile.formal_requirements if r.key == "t.education.level")
    field = next(r for r in profile.formal_requirements if r.key == "t.education.field")

    def quote(fragment):
        start = text.index(fragment)
        return Evidence(candidate_text_id=text_id, quote=fragment, start=start, end=start + len(fragment))

    assessment = repo.save_assessment(
        session, candidate_id=candidate.id, profile_id=profile.id, card_id=card.id, model="test",
        algorithm_version=ALGORITHM_VERSION, prompt_version=ASSESS_PROMPT_VERSION,
        formal_checks=[
            FormalCheckIn(requirement_id=level.id, result=CheckResult.MET, evidence=[quote("Высшее образование")],
                          alternatives=[AlternativeResultIn(key="t.education.level.alt1", result=CheckResult.MET,
                                                            evidence=[quote("Высшее образование")])]),
            FormalCheckIn(requirement_id=field.id, result=CheckResult.MET, evidence=[quote("Юриспруденция")],
                          alternatives=[
                              AlternativeResultIn(key="t.education.field.alt1", result=CheckResult.MET,
                                                  evidence=[quote("Юриспруденция")]),
                              AlternativeResultIn(key="t.education.field.alt2", result=CheckResult.UNKNOWN),
                          ]),
        ],
        competency_scores=[],
    )
    body = detail(client, application.id)
    assert body['assessment_status'] == 'mapping_required' and body['assessment'] is None
    assert body['candidate']['is_training'] is False
    response = client.get(f'/api/v1/applications/{application.id}/comparison', params={'profile_id': str(profile.id)})
    assert response.status_code == 200
    body = response.json()
    assert body['purpose'] == 'comparison' and body['assessment_status'] == 'ready'
    checks = {c["key"]: c for c in body["assessment"]["formal_checks"]}
    assert checks["t.education.field"]["is_preliminary"] is True  # по резюме, нужен документ
    assert checks["t.education.field"]["verification"] == "documents"
    assert [a["key"] for a in checks["t.education.field"]["alternatives"]] == ["t.education.field.alt1",
                                                                              "t.education.field.alt2"]
    assert checks["t.education.field"]["alternatives"][0]["evidence"][0]["utf16_start"] == text.index("Юриспруденция")
    assert checks["t.education.level"]["is_preliminary"] is False

    hr = f.make_user(session, login="hr-1")
    repo.confirm_formal_check(session, assessment_id=assessment.id, requirement_id=field.id, result=CheckResult.MET,
                              basis=VerificationMethod.DOCUMENTS, actor_user_id=hr.id, comment="диплом проверен")
    response = client.get(f'/api/v1/applications/{application.id}/comparison', params={'profile_id': str(profile.id)})
    assert response.status_code == 200
    body = response.json()
    assert body["assessment"]["version"] == 2 and body["assessment_status"] == "ready"
    confirmed = next(c for c in body["assessment"]["formal_checks"] if c["key"] == "t.education.field")
    assert (confirmed["basis"], confirmed["confirmed_by"], confirmed["is_preliminary"]) == ("documents", "hr-1", False)
    assert confirmed["evidence"] == []


# --- Фильтры -------------------------------------------------------------------

def test_filters(session, client):
    build_case(session, "C2-met")
    assert training_list(client, formal_result="met")["total"] == 1
    assert training_list(client, formal_result="not_met")["total"] == 0
    assert training_list(client, assessment_status="ready")["total"] == 1
    assert training_list(client, assessment_status="stale")["total"] == 0
    assert training_list(client, stage_code="new")["total"] == 1
    assert training_list(client, stage_code="screening")["total"] == 0
    assert training_list(client, formal_preliminary="false")["total"] == 1


def test_unknown_filter_values(session, client):
    vacancy_id = _python_vacancy_id(client)
    response = client.get(f"/api/v1/vacancies/{vacancy_id}/applications", params={"stage_code": "no-such-stage"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "UNKNOWN_STAGE_CODE"
    response = client.get(f"/api/v1/vacancies/{vacancy_id}/applications", params={"formal_result": "maybe"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_empty_application_list(client):
    vacancy_id = _python_vacancy_id(client)
    body = client.get(f"/api/v1/vacancies/{vacancy_id}/applications").json()
    assert body == {"vacancy_id": vacancy_id, "total": 0, "items": [],
                    "imported_count": 0, "confirmed_count": 0, "mismatch_count": 0,
                    "unresolved_count": 0, "not_covered_count": 0}


def test_vacancy_applications_traffic_light_ranking_and_sort(session, client):
    """Светофор и порядок откликов: группы ready/clarify/not_met/needs_action, sort=date|fit и стабильное место при фильтрах."""
    vac = f.vacancy(session, "python-dev")
    profile = f.approve(session, f.make_profile(session, position_code="python-dev", is_synthetic=True))
    edu_level = next(r for r in profile.formal_requirements if r.key == "t.education.level")
    text = "Высшее образование."

    def add_app(code: str, applied: date, check_result: CheckResult | None = None, *, make_stale: bool = False,
                posting_confirmed: bool = True):
        cand = f.make_candidate(session, code, text=text, is_synthetic=True)
        app = repo.create_application(
            session, candidate_id=cand.id, source=ApplicationSource.RESPONSE, vacancy_id=vac.id, applied_at=applied,
            posting_title=None if posting_confirmed else "Неизвестная публикация",
        )
        if posting_confirmed:
            # После requirements-03 профиль отклика берётся из подтверждённой цели публикации.
            confirm_response(session, app, "python-dev")
        if check_result is not None:
            card = f.add_card(session, cand, skills=[])
            text_id = repo.get_current_text(session, cand.id).id
            start = text.index("Высшее")
            ev = [Evidence(candidate_text_id=text_id, quote="Высшее", start=start, end=start + len("Высшее"))] if check_result != CheckResult.UNKNOWN else []
            repo.save_assessment(
                session, candidate_id=cand.id, profile_id=profile.id, card_id=card.id, model="test",
                algorithm_version=ALGORITHM_VERSION, prompt_version=ASSESS_PROMPT_VERSION,
                formal_checks=[FormalCheckIn(requirement_id=edu_level.id, result=check_result, evidence=ev)],
                competency_scores=[],
            )
            if make_stale:
                repo.add_candidate_text(session, cand.id, text="Обновлённый текст.", redaction_method="test-v2")
        return app

    add_app("py-ready", date(2026, 11, 10), CheckResult.MET)
    add_app("py-clarify", date(2026, 11, 16), CheckResult.UNKNOWN)
    add_app("py-unassessed", date(2026, 11, 17), None)
    add_app("py-not-met", date(2026, 11, 18), CheckResult.NOT_MET)
    add_app("py-stale", date(2026, 11, 20), CheckResult.MET, make_stale=True)
    # Оценка есть, но цель публикации не подтверждена: профиль отклика не определён — светофор ⚪.
    add_app("py-unmapped", date(2026, 11, 19), CheckResult.MET, posting_confirmed=False)

    # По умолчанию sort=date: порядок по дате убыванию, но места и причины светофора уже посчитаны.
    by_date = training_list(client)
    assert [i["candidate_code"] for i in by_date["items"]] == [
        "py-stale", "py-unmapped", "py-not-met", "py-unassessed", "py-clarify", "py-ready"
    ]
    ranks_by_code = {
        i["candidate_code"]: (i["rank_group"], i["rank_position"], i["rank_reason"])
        for i in by_date["items"]
    }
    assert ranks_by_code["py-ready"][:2] == ("ready", 1)
    assert "Все обязательные подтверждены" in ranks_by_code["py-ready"][2]
    assert ranks_by_code["py-clarify"][:2] == ("clarify", 2)
    assert "Высшее образование" in ranks_by_code["py-clarify"][2]
    assert ranks_by_code["py-not-met"][:2] == ("not_met", 3)
    assert ranks_by_code["py-not-met"][2] == "Не проходит: образование — «Высшее»"
    assert ranks_by_code["py-unassessed"] == ("needs_action", None, "Нужна оценка: отклик ещё не оценивался")
    assert ranks_by_code["py-stale"] == ("needs_action", None, "Нужна переоценка: резюме, профиль или алгоритм изменились")
    assert ranks_by_code["py-unmapped"][:2] == ("needs_action", None)
    assert ranks_by_code["py-unmapped"][2].startswith("Публикация не сопоставлена с должностью")

    # Явный sort=fit: зелёные -> жёлтые -> красные -> серые (на одном уровне даты более ранний сначала).
    by_fit = training_list(client, sort="fit")
    assert [i["candidate_code"] for i in by_fit["items"]] == [
        "py-ready", "py-clarify", "py-not-met", "py-unassessed", "py-unmapped", "py-stale"
    ]
    assert [i["rank_position"] for i in by_fit["items"]] == [1, 2, 3, None, None, None]

    # Фильтр сохраняет честное место внутри всей вакансии.
    filtered = training_list(client, formal_result="not_met", sort="fit")
    assert [i["candidate_code"] for i in filtered["items"]] == ["py-not-met"]
    assert filtered["items"][0]["rank_position"] == 3

    bad_sort = client.get(f"/api/v1/vacancies/{vac.id}/applications", params={"contour": "training", "sort": "unknown"})
    assert bad_sort.status_code == 422 and bad_sort.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Ошибки --------------------------------------------------------------------

@pytest.mark.parametrize("path, code", [
    ("/api/v1/vacancies/{id}/applications", "VACANCY_NOT_FOUND"),
    ("/api/v1/applications/{id}", "APPLICATION_NOT_FOUND"),
    ("/api/v1/candidate-texts/{id}", "CANDIDATE_TEXT_NOT_FOUND"),
])
def test_missing_entity_is_404_in_common_format(client, path, code):
    response = client.get(path.format(id=uuid.uuid4()))
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == code and error["message"] and isinstance(error["details"], dict)


def test_malformed_uuid_is_422_in_common_format(client):
    response = client.get("/api/v1/applications/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "not-a-uuid" not in response.text  # ответ не повторяет ввод


def test_unknown_route_uses_common_format(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


# --- Слепой режим --------------------------------------------------------------

def test_no_pii_or_raw_text_in_any_response(session, client):
    built = build_case(session, "C5-non-bmp")
    # raw_text исходного документа содержит маркер и ПДн; ответы не должны их показать.
    candidate = session.get(Candidate, built["candidate_id"])
    candidate.source_document.raw_text += f"\n{RAW_MARKER} {PII['full_name']} {PII['phone']}"
    session.flush()

    application = detail(client, built["application_id"])
    text_ids = {application["candidate"]["current_text_id"]} | {
        e["candidate_text_id"] for s in application["assessment"]["competency_scores"] for e in s["evidence"]
    }
    vacancy_id = application["vacancy"]["vacancy_id"]
    responses = [
        client.get("/api/v1/vacancies", params={"contour": "training"}),
        client.get(f"/api/v1/vacancies/{vacancy_id}/applications", params={"contour": "training"}),
        client.get(f"/api/v1/applications/{built['application_id']}"),
        *[client.get(f"/api/v1/candidate-texts/{text_id}") for text_id in text_ids],
    ]
    for response in responses:
        assert response.status_code == 200
        dumped = json.dumps(response.json(), ensure_ascii=False)
        for value in [*PII.values(), RAW_MARKER, "raw_text", "full_name", "birth_date"]:
            assert value not in dumped, f"{value!r} в ответе {response.url}"


def test_hr_sees_candidate_contacts_and_each_view_is_journaled(session, client):
    """Кадровик видит контакты в карточке отклика (решение команды с HR); чтение пишется в журнал.
    Анонимное чтение остаётся слепым, исходный текст резюме по-прежнему не отдаётся."""
    from sqlalchemy import func, select

    from app.db.enums import AuditAction
    from app.db.models import AuditLog
    from app.db.seed import seed_demo_users

    seed_demo_users(session)
    built = build_case(session, "C5-non-bmp")
    views = lambda: session.scalar(select(func.count()).select_from(AuditLog).where(  # noqa: E731
        AuditLog.action == AuditAction.VIEW_PII, AuditLog.entity_id == str(built["candidate_id"])))
    before = views()
    hr = client.get(f"/api/v1/applications/{built['application_id']}", headers={"X-User-Login": "hr_demo"}).json()
    assert hr["candidate"]["pii_hidden"] is False
    assert hr["candidate"]["contacts"] == {"full_name": PII["full_name"], "phone": PII["phone"],
                                           "email": PII["email"], "city": PII["city"]}
    assert views() == before + 1
    assert "raw_text" not in json.dumps(hr, ensure_ascii=False)
    anonymous = detail(client, built["application_id"])
    assert anonymous["candidate"]["contacts"] is None and anonymous["candidate"]["pii_hidden"] is True
    assert views() == before + 1
