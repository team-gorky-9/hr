"""HTTP API действий кадровика, резерва, кросс-оценок и воронки (api.md v0.3, раздел 3; backend-02).

Данные создаются настоящими функциями repository; пользователи — учётки стенда из seed
(hr_demo, dept_demo, admin_demo), их загружает conftest вместе со справочниками.
Учебный кандидат py-9001 берётся из контрольного набора, как в tests/test_api.py.

Гонки (две вкладки, два запроса в резерв) проверяются отдельно на настоящих параллельных
транзакциях: данные для них фиксируются commit и удаляются после теста.
"""
import json
import threading
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.api import workflow
from app.assessment.prompts import ASSESS_PROMPT_VERSION
from app.assessment.version import ALGORITHM_VERSION
from app.api.schemas import Contour, ReserveIn
from app.db import repository as repo
from app.db.enums import ApplicationSource, Channel, ReserveStatus, RowOrigin, UserRole, VerificationMethod
from app.db.models import (
    Application, Assessment, Candidate, RequirementProfile, ReserveEntry, SourceDocument, StageEvent, User, Vacancy,
)
from app.db.session import get_session
from app.main import create_app
from app.schemas.assessment import CompetencyScoreIn
from app.schemas.card import Evidence
from app.schemas.requirements import CompetencyIn, IndicatorIn
from tests import factories as f
from tests.posting_helpers import posting_registry  # noqa: F401 (fixture used by imported client)
from tests.test_api import PII, build_case, client  # noqa: F401  (client — фикстура)
from tests.test_assessment_fixtures_db import _load_profile

HR = {"X-User-Login": "hr_demo"}
DEPT = {"X-User-Login": "dept_demo"}
ADMIN = {"X-User-Login": "admin_demo"}
BASIS = {"reason": "Сильные API-тесты, не хватило стажа", "contact_basis": "Вернуться при новой вакансии QA"}


def error_code(response) -> str:
    return response.json()["error"]["code"]


def history(client, application_id) -> dict:
    response = client.get(f"/api/v1/applications/{application_id}/history", headers=HR)
    assert response.status_code == 200, response.text
    return response.json()


def handoff_payload(client, application_id, headers=HR, **extra) -> dict:
    """Сформировать блок передачи по актуальному summary_revision для перевода в sent_to_department."""
    summary = client.get(f"/api/v1/applications/{application_id}/handoff-summary", headers=headers)
    assert summary.status_code == 200, summary.text
    return {
        "recipient_name": "Руководитель департамента",
        "recipient_department": "Департамент-заказчик (учебный)",
        "channel": "sed",
        "summary_revision": summary.json()["summary_revision"],
        "request_id": str(uuid.uuid4()),
        **extra,
    }


def move(client, application_id, to_stage, headers=HR, expected_seq=None, **body):
    """Перевод этапа так, как это делает форма: expected_seq — из последней прочитанной истории."""
    if expected_seq is None:
        expected_seq = history(client, application_id)["last_seq"]
    if to_stage == "sent_to_department" and "handoff" not in body:
        body["handoff"] = handoff_payload(client, application_id)
    return client.post(f"/api/v1/applications/{application_id}/stage", headers=headers,
                       json={"to_stage_code": to_stage, "expected_seq": expected_seq, **body})


def no_pii(response) -> None:
    dumped = json.dumps(response.json(), ensure_ascii=False)
    for value in [*PII.values(), '"full_name":', '"birth_date":', '"phone":', '"email":']:
        assert value not in dumped, f"{value!r} в ответе {response.url}"


def application(session, code: str, *, source=ApplicationSource.RESPONSE, position="python-dev", candidate=None):
    candidate = candidate or f.make_candidate(session, code)
    kwargs = {"vacancy_id": f.vacancy(session, position).id}
    if source == ApplicationSource.HISTORY:
        kwargs = {"external_position_title": "Начальник отдела (из истории)"}
    return repo.create_application(session, candidate_id=candidate.id, source=source, **kwargs)


def reserve_body(candidate_id, position_id, **extra) -> dict:
    return {"candidate_id": str(candidate_id), "position_id": str(position_id), **BASIS, **extra}


def _user(session, login: str) -> User:
    return session.scalar(select(User).where(User.login == login))


# --- Сценарии 1–2 приёмки: путь py-9001 до отказа и резерва ---------------------------

def test_py9001_path_to_rejection_and_reserve(session, client):
    """new → screening → phone_interview → sent_to_department → rejected(experience) → резерв на QA;
    повтор из финала — 409, второй отклик того же человека живёт своей историей."""
    built = build_case(session, "C1-unknown")
    app_id = built["application_id"]
    candidate = session.get(Candidate, built["candidate_id"])
    second = application(session, "", position="qa-manual", candidate=candidate).id

    for stage in ("screening", "phone_interview", "sent_to_department"):
        response = move(client, app_id, stage)
        assert response.status_code == 201, response.text
        assert response.json()["event"]["actor"] == {"login": "hr_demo", "role": "hr"}

    rejected = move(client, app_id, "rejected", rejection_reason_code="experience", comment="Стаж меньше двух лет")
    assert rejected.status_code == 201, rejected.text
    assert rejected.json()["stage"] == {"code": "rejected", "title": "Отказ", "is_final": True}

    body = history(client, app_id)
    assert [e["to_stage"]["code"] for e in body["items"]] == [
        "new", "screening", "phone_interview", "sent_to_department", "rejected"]
    assert body["items"][0]["actor"] is None  # отклик создал импорт
    assert body["items"][-1]["rejection_reason"]["code"] == "experience"
    assert body["items"][-1]["actor"]["login"] == "hr_demo"
    assert body["last_seq"] == body["items"][-1]["seq"]

    again = move(client, app_id, "screening")
    assert (again.status_code, error_code(again)) == (409, "STAGE_TRANSITION_CONFLICT")
    assert again.json()["error"]["message"] == "Отбор уже завершён на этапе «Отказ»"
    assert history(client, second)["stage"]["code"] == "new"  # второй отклик не тронут

    qa = f.position(session, "qa-manual")
    applications_before = session.scalar(select(func.count()).select_from(Application))
    reserve = client.post("/api/v1/reserve", headers=HR, json=reserve_body(
        candidate.id, qa.id, source_application_id=str(app_id),
        valid_until=(date.today() + timedelta(days=180)).isoformat()))
    assert reserve.status_code == 201, reserve.text
    entry = reserve.json()["entry"]
    assert entry["contact_basis"] == BASIS["contact_basis"] and entry["added_by"]["login"] == "hr_demo"
    listed = client.get(f"/api/v1/positions/{qa.id}/reserve", params={"contour": "training"}, headers=HR).json()
    assert [e["candidate_code"] for e in listed["items"]] == ["py-9001"]
    # Учебный кандидат не попадает в рабочий резерв; резерв откликов не создаёт.
    assert client.get(f"/api/v1/positions/{qa.id}/reserve", headers=HR).json()["total"] == 0
    assert session.scalar(select(func.count()).select_from(Application)) == applications_before


def test_stale_form_from_second_tab_is_409(session, client):
    app_id = application(session, "py-0300").id
    seen = history(client, app_id)["last_seq"]
    assert move(client, app_id, "screening", expected_seq=seen).status_code == 201
    stale = move(client, app_id, "rejected", expected_seq=seen, rejection_reason_code="no_response")
    assert (stale.status_code, error_code(stale)) == (409, "STALE_STAGE_FORM")
    assert stale.json()["error"]["details"]["current_stage_code"] == "screening"
    assert [e["to_stage"]["code"] for e in history(client, app_id)["items"]] == ["new", "screening"]


def test_stage_input_errors_are_422(session, client):
    app_id = application(session, "py-0301").id
    seq = history(client, app_id)["last_seq"]
    cases = [
        ({"to_stage_code": "nope"}, "UNKNOWN_STAGE_CODE"),
        ({"to_stage_code": "rejected", "rejection_reason_code": "nope"}, "UNKNOWN_REJECTION_REASON"),
        ({"to_stage_code": "screening", "rejection_reason_code": "experience"}, "REJECTION_REASON_NOT_ALLOWED"),
        ({"to_stage_code": "rejected"}, "REJECTION_REASON_REQUIRED"),
        ({"to_stage_code": "withdrawn"}, "REJECTION_REASON_REQUIRED"),
    ]
    for body, code in cases:
        response = client.post(f"/api/v1/applications/{app_id}/stage", json={"expected_seq": seq, **body}, headers=HR)
        assert (response.status_code, error_code(response)) == (422, code), body
    no_seq = client.post(f"/api/v1/applications/{app_id}/stage", json={"to_stage_code": "screening"}, headers=HR)
    assert (no_seq.status_code, error_code(no_seq)) == (422, "VALIDATION_ERROR")
    assert history(client, app_id)["last_seq"] == seq


def test_stage_skip_needs_confirmation_and_comment(session, client):
    app_id = application(session, "py-0302").id
    assert error_code(move(client, app_id, "sent_to_department")) == "STAGE_TRANSITION_CONFLICT"
    assert move(client, app_id, "sent_to_department", confirm_skip=True, comment="  ").status_code == 409
    confirmed = move(client, app_id, "sent_to_department", confirm_skip=True, comment="Рекомендация департамента")
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["event"]["from_stage"]["code"] == "new"
    assert move(client, app_id, "sent_to_department").status_code == 409  # тот же этап


def test_history_and_manual_applications_are_not_worked(session, client):
    """Отклики history и manual: рабочие действия по ID отклоняются, историю читать можно."""
    external = application(session, "py-0303", source=ApplicationSource.HISTORY).id
    manual = application(session, "py-0304", source=ApplicationSource.MANUAL).id
    for app_id in (external, manual):
        response = move(client, app_id, "screening")
        assert (response.status_code, error_code(response)) == (409, "NOT_WORKING_APPLICATION")
    assert history(client, external)["source"] == "history"


def test_roles(session, client):
    app_id = application(session, "py-0305").id
    f.make_user(session, login="hr-off", active=False)
    cases = [({}, 401, "USER_REQUIRED"), ({"X-User-Login": "ghost"}, 401, "UNKNOWN_USER"),
             ({"X-User-Login": "hr-off"}, 401, "UNKNOWN_USER"), (DEPT, 403, "FORBIDDEN_ROLE")]
    for headers, status, code in cases:
        response = move(client, app_id, "screening", headers=headers, expected_seq=1)
        assert (response.status_code, error_code(response)) == (status, code), headers
    assert move(client, app_id, "screening", headers=ADMIN).status_code == 201


def test_department_gets_nothing_by_direct_id(session, client):
    """Сценарий 4: область доступа департамента не согласована — по прямому ID роль department данных не получает."""
    built = build_case(session, "C1-unknown")
    position_id = f.position(session).id
    urls = [
        f"/api/v1/applications/{built['application_id']}/history",
        f"/api/v1/candidates/{built['candidate_id']}/cross-assessments",
        f"/api/v1/positions/{position_id}/reserve",
        "/api/v1/analytics/funnel",
        "/api/v1/references/stages",
    ]
    for url in urls:
        response = client.get(url, headers=DEPT)
        assert (response.status_code, error_code(response)) == (403, "FORBIDDEN_ROLE"), url
        assert "py-9001" not in response.text
        assert client.get(url).status_code == 401


def test_references(client):
    stages = client.get("/api/v1/references/stages", headers=HR).json()["items"]
    assert [s["code"] for s in stages][:3] == ["new", "screening", "phone_interview"]
    assert {s["code"] for s in stages if s["is_final"]} == {"hired", "rejected", "withdrawn"}
    reasons = client.get("/api/v1/references/rejection-reasons", headers=HR).json()["items"]
    assert {"experience", "no_response", "other"} <= {r["code"] for r in reasons}


# --- Резерв --------------------------------------------------------------------------

def test_reserve_rules(session, client):
    built = build_case(session, "C1-unknown")
    candidate_id, pos = built["candidate_id"], f.position(session)
    other = application(session, "py-0310").id
    external = application(session, "", source=ApplicationSource.HISTORY,
                           candidate=session.get(Candidate, candidate_id)).id

    cases = [
        ({"candidate_id": str(candidate_id), **BASIS}, 422, "RESERVE_TARGET_REQUIRED"),
        (reserve_body(candidate_id, pos.id, reason=" "), 422, "RESERVE_BASIS_REQUIRED"),
        (reserve_body(candidate_id, pos.id, contact_basis=None), 422, "RESERVE_BASIS_REQUIRED"),
        (reserve_body(candidate_id, pos.id, valid_until=(date.today() - timedelta(days=1)).isoformat()),
         422, "RESERVE_VALID_UNTIL_IN_PAST"),
        (reserve_body(candidate_id, pos.id, source_application_id=str(other)), 422, "APPLICATION_OF_OTHER_CANDIDATE"),
        (reserve_body(candidate_id, pos.id, source_application_id=str(external)), 409, "NOT_WORKING_APPLICATION"),
        (reserve_body(uuid.uuid4(), pos.id), 404, "CANDIDATE_NOT_FOUND"),
        (reserve_body(candidate_id, uuid.uuid4()), 404, "POSITION_NOT_FOUND"),
    ]
    for body, status, code in cases:
        response = client.post("/api/v1/reserve", headers=HR, json=body)
        assert (response.status_code, error_code(response)) == (status, code), body
    assert session.scalar(select(func.count()).select_from(ReserveEntry)) == 0
    assert client.post("/api/v1/reserve", headers=DEPT, json=reserve_body(candidate_id, pos.id)).status_code == 403

    first = client.post("/api/v1/reserve", headers=HR, json=reserve_body(candidate_id, pos.id))
    again = client.post("/api/v1/reserve", headers=HR, json=reserve_body(candidate_id, pos.id))
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["created"] is False
    assert again.json()["entry"]["reserve_id"] == first.json()["entry"]["reserve_id"]
    area = client.post("/api/v1/reserve", headers=HR,
                       json={"candidate_id": str(candidate_id), "competency_area": "Тестирование", **BASIS})
    assert area.status_code == 201 and area.json()["entry"]["position_id"] is None


def test_reserve_last_allowed_day_expiry_and_new_period(session, posting_registry):
    """Запись видна в последний разрешённый день, после срока пропадает; новый период — своё происхождение."""
    built = build_case(session, "C1-unknown")
    candidate_id, pos = built["candidate_id"], f.position(session)
    last_day = date(2026, 12, 31)
    first = workflow.add_to_reserve(session, ReserveIn(**reserve_body(candidate_id, pos.id, valid_until=last_day)),
                                    _user(session, "hr_demo"), today=date(2026, 11, 20))
    assert first.created is True
    on_last_day = workflow.list_reserve(session, pos.id, Contour.TRAINING, today=last_day)
    assert [e.reserve_id for e in on_last_day.items] == [first.entry.reserve_id]
    day_after = last_day + timedelta(days=1)
    assert workflow.list_reserve(session, pos.id, Contour.TRAINING, today=day_after).items == []
    # То же правило активности — для фильтра поиска (search-01).
    active = set(session.scalars(select(ReserveEntry.id).where(repo.active_reserve_condition(day_after))))
    assert first.entry.reserve_id not in active

    renewed = workflow.add_to_reserve(
        session, ReserveIn(**reserve_body(candidate_id, pos.id, reason="Прошёл курс по API",
                                          contact_basis="Новая вакансия QA в феврале")),
        _user(session, "admin_demo"), today=day_after)
    assert renewed.created is True and renewed.entry.reserve_id != first.entry.reserve_id
    old = session.get(ReserveEntry, first.entry.reserve_id)
    assert old.status == ReserveStatus.EXPIRED and old.end_reason == "срок резерва истёк" and old.ended_at is not None
    assert renewed.entry.added_by.login == "admin_demo" and renewed.entry.reason == "Прошёл курс по API"


def test_reserve_withdrawal(session, client):
    built = build_case(session, "C1-unknown")
    pos = f.position(session)
    reserve_id = client.post("/api/v1/reserve", headers=HR,
                             json=reserve_body(built["candidate_id"], pos.id)).json()["entry"]["reserve_id"]
    url = f"/api/v1/reserve/{reserve_id}/withdraw"
    assert error_code(client.post(url, headers=HR, json={"reason": " "})) == "WITHDRAW_REASON_REQUIRED"
    withdrawn = client.post(url, headers=HR, json={"reason": "Кандидат трудоустроен в другом месте"})
    assert withdrawn.status_code == 200, withdrawn.text
    body = withdrawn.json()
    assert body["status"] == "withdrawn" and body["ended_by"]["login"] == "hr_demo"
    listed = client.get(f"/api/v1/positions/{pos.id}/reserve", params={"contour": "training"}, headers=HR).json()
    assert listed["total"] == 0
    assert error_code(client.post(url, headers=HR, json={"reason": "ещё раз"})) == "RESERVE_NOT_ACTIVE"
    assert client.post(f"/api/v1/reserve/{uuid.uuid4()}/withdraw", headers=HR, json={"reason": "x"}).status_code == 404
    # Возобновление — новая запись с новым основанием; отозванная остаётся в истории.
    renewed = client.post("/api/v1/reserve", headers=HR, json=reserve_body(built["candidate_id"], pos.id))
    assert renewed.status_code == 201 and renewed.json()["entry"]["reserve_id"] != reserve_id
    assert session.scalar(select(func.count()).select_from(ReserveEntry)) == 2


# --- Воронка --------------------------------------------------------------------------

def test_funnel_counts_match_records(session, client):
    """Сценарий с известными числами; учебные, внешние и ручные отклики и другие вакансии не входят."""
    a = application(session, "py-0201").id  # new → screening
    b = application(session, "py-0202").id  # … → sent_to_department
    d = application(session, "py-0204").id  # new → rejected(experience)
    e = application(session, "py-0205").id  # new → withdrawn(no_response)
    application(session, "py-0206")  # остаётся new
    application(session, "py-0207", source=ApplicationSource.HISTORY)
    application(session, "py-0208", source=ApplicationSource.MANUAL)
    other = application(session, "qa-0209", position="qa-manual").id
    training = build_case(session, "C1-unknown")["application_id"]

    assert move(client, a, "screening").status_code == 201
    for app_id in (b, other, training):
        for stage in ("screening", "phone_interview", "sent_to_department"):
            assert move(client, app_id, stage).status_code == 201
    assert move(client, d, "rejected", rejection_reason_code="experience").status_code == 201
    assert move(client, e, "withdrawn", rejection_reason_code="no_response").status_code == 201

    vacancy_id = str(f.vacancy(session).id)
    funnel = client.get("/api/v1/analytics/funnel", params={"vacancy_id": vacancy_id}, headers=HR).json()
    assert funnel["total_applications"] == 5
    stages = {s["code"]: (s["current_count"], s["reached_count"]) for s in funnel["stages"]}
    assert stages["new"] == (1, 5)
    assert stages["screening"] == (1, 2)
    assert stages["phone_interview"] == (0, 1)
    assert stages["sent_to_department"] == (1, 1)
    assert stages["rejected"] == (1, 1) and stages["withdrawn"] == (1, 1) and stages["hired"] == (0, 0)
    closures = {(c["stage_code"], c["reason_code"]): c["count"] for c in funnel["closures"]}
    assert closures == {("rejected", "experience"): 1, ("withdrawn", "no_response"): 1}
    assert funnel["closures_without_reason"] == 0
    assert funnel["open_waits"]["total"] == 1
    assert funnel["open_waits"]["unique_applications"] == 1
    assert funnel["timezone"] == "Europe/Moscow"

    assert client.get("/api/v1/analytics/funnel", headers=HR).json()["total_applications"] == 6
    by_position = client.get("/api/v1/analytics/funnel", headers=HR,
                             params={"position_id": str(f.position(session, "qa-manual").id)}).json()
    assert by_position["total_applications"] == 1
    training_funnel = client.get("/api/v1/analytics/funnel", params={"contour": "training"}, headers=HR).json()
    assert training_funnel["total_applications"] == 1
    assert client.get("/api/v1/analytics/funnel", params={"vacancy_id": str(uuid.uuid4())}, headers=HR).status_code == 404

    # Сверка с базой напрямую: события «new» по откликам выборки.
    assert session.scalar(select(func.count()).select_from(StageEvent).where(
        StageEvent.application_id.in_([a, b, d, e]), StageEvent.to_stage_code == "new")) == 4


def test_funnel_period_and_unknown_historical_reasons(session, client):
    """Период закрытий по МСК; старый отказ без причины виден как «не указана»; пустая выборка — нули."""
    late = application(session, "py-0220").id
    early = application(session, "py-0221").id
    assert move(client, late, "rejected", rejection_reason_code="experience").status_code == 201
    # Историческая запись: отказ без причины 19.11 в 23:30 по Москве (= 20:30 UTC).
    repo.move_application(session, early, "rejected")
    session.execute(update(StageEvent).where(StageEvent.application_id == early, StageEvent.to_stage_code == "rejected")
                    .values(created_at=datetime(2026, 11, 19, 20, 30, tzinfo=timezone.utc)))
    session.flush()

    def closures(**params):
        body = client.get("/api/v1/analytics/funnel", headers=HR, params=params).json()
        return {(c["reason_code"], c["reason_title"]): c["count"] for c in body["closures"]}, body

    on_19th, body = closures(period_from="2026-11-19", period_to="2026-11-19")
    assert on_19th == {(None, "Причина не указана"): 1}
    assert body["closures_without_reason"] == 1
    everything, _ = closures()
    assert everything[("experience", "Недостаточно профессионального опыта")] == 1
    bad = client.get("/api/v1/analytics/funnel", headers=HR,
                     params={"period_from": "2026-11-20", "period_to": "2026-11-19"})
    assert (bad.status_code, error_code(bad)) == (422, "INVALID_PERIOD")
    empty = client.get("/api/v1/analytics/funnel", headers=HR,
                       params={"vacancy_id": str(f.vacancy(session, "junior-ux-ui").id)}).json()
    assert empty["total_applications"] == 0 and empty["closures"] == []
    assert all(s["current_count"] == 0 and s["reached_count"] == 0 for s in empty["stages"])


def test_period_bounds_use_moscow_time():
    start, end = workflow.period_bounds(date(2026, 11, 19), date(2026, 11, 19))
    assert start.astimezone(timezone.utc) == datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc)
    assert end.astimezone(timezone.utc) == datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)


# --- Кросс-оценки ---------------------------------------------------------------------

def _approved_training_profile(session, position_code: str):
    team = {"origin": RowOrigin.TEAM, "note": "тестовые данные"}
    profile = repo.create_requirement_profile(
        session, position_id=f.position(session, position_code).id, created_by="test", is_synthetic=True,
        formal_requirements=[],
        competencies=[CompetencyIn(key=f"{position_code}.api", code="API_TEST", name="Тестирование API",
                                   target_level_min=60, target_level_max=100, **team,
                                   indicators=[IndicatorIn(key=f"{position_code}.api.1", text="пишет API-тесты",
                                                           verification=VerificationMethod.RESUME, **team)])],
    )
    return f.approve(session, profile)


def test_cross_assessments_over_all_approved_profiles(session, client):
    """Маршрут отдаёт модель чтения ai-02: три утверждённых профиля, порядок, цитата, отклики не создаются."""
    built = build_case(session, "C1-unknown")  # отклик и оценка по python-dev
    qa = _approved_training_profile(session, "qa-manual")
    _approved_training_profile(session, "frontend-dev")  # утверждён, но не оценён
    card = repo.get_current_card(session, built["candidate_id"])
    text = repo.get_current_text(session, built["candidate_id"])
    quote = "Написал API-тесты"
    repo.save_assessment(
        session, candidate_id=built["candidate_id"], profile_id=qa.id, card_id=card.id, model="test",
        formal_checks=[], overall_score=90,
        algorithm_version=ALGORITHM_VERSION, prompt_version=ASSESS_PROMPT_VERSION,
        competency_scores=[CompetencyScoreIn(
            competency_id=qa.competencies[0].id, level=90, explanation="пишет API-тесты",
            evidence=[Evidence(candidate_text_id=text.id, quote=quote, start=0, end=len(quote))])],
    )
    applications_before = session.scalar(select(func.count()).select_from(Application))

    response = client.get(f"/api/v1/candidates/{built['candidate_id']}/cross-assessments", headers=HR)
    assert response.status_code == 200, response.text
    no_pii(response)
    body = response.json()
    assert body["candidate_code"] == "py-9001" and body["is_training"] is True and body["empty_reason"] is None
    by_code = {i["position_code"]: i for i in body["items"]}
    assert set(by_code) == {"python-dev", "qa-manual", "frontend-dev"}
    assert body["items"][-1]["position_code"] == "frontend-dev"  # не оценённые в конце
    assert by_code["frontend-dev"]["assessment_status"] == "not_assessed" and by_code["frontend-dev"]["assessment"] is None

    qa_item = by_code["qa-manual"]
    assert qa_item["assessment_status"] == "ready" and qa_item["is_training"] is True
    assert qa_item["is_source_position"] is False
    assert [v["application_id"] for v in qa_item["vacancies"]] == [None]
    assert qa_item["position_id"] == str(f.position(session, "qa-manual").id)
    [competency] = qa_item["assessment"]["competencies"]
    assert (competency["code"], competency["name"], competency["level"]) == ("API_TEST", "Тестирование API", 90)
    [evidence] = competency["evidence"]
    assert evidence["quote"] == quote and evidence["candidate_text_id"] == str(text.id)  # цитата ведёт к своей версии
    assert (evidence["utf16_start"], evidence["utf16_end"]) == (0, len(quote))
    python_item = by_code["python-dev"]
    assert python_item["is_source_position"] is True
    [python_vacancy] = python_item["vacancies"]
    assert python_vacancy["application_id"] == str(built["application_id"])
    assert python_vacancy["application_stage_code"] == "new"
    assert python_item["assessment"]["formal_result"] == "unknown"

    assert session.scalar(select(func.count()).select_from(Application)) == applications_before
    missing = client.get(f"/api/v1/candidates/{uuid.uuid4()}/cross-assessments", headers=HR)
    assert (missing.status_code, error_code(missing)) == (404, "CANDIDATE_NOT_FOUND")


def test_cross_assessments_empty_is_not_error(session, client):
    candidate = f.make_candidate(session, "py-0400")
    response = client.get(f"/api/v1/candidates/{candidate.id}/cross-assessments", headers=HR)
    assert response.status_code == 200
    assert response.json()["items"] == [] and response.json()["empty_reason"] == "no_approved_profiles"


def test_cross_assessments_mark_each_vacancy_of_position(session, client):
    """У должности две вакансии: отклик показан только у своей, вторая — без отклика; history
    и manual не делают должность «своей» (is_source_position)."""
    built = build_case(session, "C1-unknown")
    candidate = session.get(Candidate, built["candidate_id"])
    second = Vacancy(position_id=f.position(session).id, channel=Channel.CITY_SITE, title="Python-разработчик (сайт)")
    third = Vacancy(position_id=f.position(session).id, channel=Channel.EMAIL, title="Python-разработчик (почта)")
    session.add_all([second, third])
    session.flush()
    manual = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.MANUAL,
                                     vacancy_id=second.id)
    body = client.get(f"/api/v1/candidates/{built['candidate_id']}/cross-assessments", headers=HR).json()
    [item] = body["items"]
    linked = {v["vacancy_id"]: (v["application_id"], v["application_source"]) for v in item["vacancies"]}
    assert linked == {str(f.vacancy(session).id): (str(built["application_id"]), "response"),
                      str(second.id): (None, None), str(third.id): (None, None)}
    assert item["is_source_position"] is True
    assert {a["application_id"] for a in body["applications"]} == {str(built["application_id"]), str(manual.id)}


def test_cross_and_application_list_agree_on_stale_status(session, client):
    """Одно правило актуальности: оценка со старой версией промпта устарела и в списке, и в рекомендациях."""
    built = build_case(session, "C1-unknown")
    assessment = session.get(Assessment, built["assessment_id"])
    assessment.prompt_version = "old-prompt"
    session.flush()
    listed = client.get(f"/api/v1/vacancies/{f.vacancy(session).id}/applications",
                        params={"contour": "training"}).json()["items"][0]
    [item] = client.get(f"/api/v1/candidates/{built['candidate_id']}/cross-assessments", headers=HR).json()["items"]
    assert (listed["assessment_status"], item["assessment_status"], item["stale_reason"]) == (
        "stale", "stale", "algorithm_changed")


def test_cross_quotes_of_previous_text_version_have_utf16(session, client):
    """Цитата устаревшей оценки ссылается на прежнюю версию текста, и границы UTF-16 считаются по ней."""
    built = build_case(session, "C5-non-bmp")  # эмодзи перед цитатой: UTF-16 сдвинут на 1
    repo.add_candidate_text(session, built["candidate_id"], text="Новая очистка.", redaction_method="test-v2")
    [item] = client.get(f"/api/v1/candidates/{built['candidate_id']}/cross-assessments", headers=HR).json()["items"]
    assert item["stale_reason"] == "text_changed"
    [evidence] = item["assessment"]["competencies"][0]["evidence"]
    assert evidence["candidate_text_id"] == str(built["text_id"])
    assert (evidence["utf16_start"], evidence["utf16_end"]) == (evidence["start"] + 1, evidence["end"] + 1)


# --- Без ПДн и состав OpenAPI ----------------------------------------------------------

def test_stage_2_responses_do_not_leak_pii(session, client):
    built = build_case(session, "C5-non-bmp")
    app_id, candidate_id, pos = built["application_id"], built["candidate_id"], f.position(session)
    move(client, app_id, "screening", comment="ок")
    client.post("/api/v1/reserve", headers=HR, json=reserve_body(candidate_id, pos.id))
    for url in [f"/api/v1/applications/{app_id}/history", f"/api/v1/candidates/{candidate_id}/cross-assessments",
                f"/api/v1/positions/{pos.id}/reserve?contour=training", "/api/v1/analytics/funnel?contour=training"]:
        response = client.get(url, headers=HR)
        assert response.status_code == 200, url
        no_pii(response)


def test_demo_users_are_seeded(session):
    roles = dict(session.execute(select(User.login, User.role).where(User.login.like("%_demo"))).all())
    assert roles == {
        "hr_demo": UserRole.HR,
        "dept_demo": UserRole.DEPARTMENT,
        "dept2_demo": UserRole.DEPARTMENT,
        "admin_demo": UserRole.ADMIN,
    }


def test_openapi_has_stage_2_routes_and_no_pii_route(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/references/stages": {"get"},
        "/api/v1/references/rejection-reasons": {"get"},
        "/api/v1/applications/{application_id}/stage": {"post"},
        "/api/v1/applications/{application_id}/history": {"get"},
        "/api/v1/candidates/{candidate_id}/cross-assessments": {"get"},
        "/api/v1/reserve": {"post"},
        "/api/v1/reserve/{reserve_id}/withdraw": {"post"},
        "/api/v1/positions/{position_id}/reserve": {"get"},
        "/api/v1/analytics/funnel": {"get"},
        "/api/v1/applications/{application_id}/handoff-summary": {"get"},
        "/api/v1/applications/{application_id}/handoffs": {"get", "post"},
        "/api/v1/applications/{application_id}/handoffs/{attempt_id}/deadline": {"post"},
        "/api/v1/handoffs": {"get"},
        "/api/v1/handoffs/{attempt_id}": {"get"},
        "/api/v1/applications/{application_id}/feedback": {"get", "post"},
    }
    for path, methods in expected.items():
        assert set(paths[path]) == methods, path
    assert not [p for p in paths if "pii" in p]
    # Маршруты интервью — из interview-01 (interview.md v0.4) и итог встречи (wave-2-stage-1).
    assert {p for p in paths if "interview" in p} == {
        "/api/v1/applications/{application_id}/interview-guide",
        "/api/v1/interviews/{interview_id}/questions/{question_id}/answers",
        "/api/v1/applications/{application_id}/interviews",
        "/api/v1/interviews/{interview_id}/outcome",
    }


def test_unknown_application_history_is_404(client):
    response = client.get(f"/api/v1/applications/{uuid.uuid4()}/history", headers=HR)
    assert (response.status_code, error_code(response)) == (404, "APPLICATION_NOT_FOUND")


# --- Настоящие гонки: две транзакции одновременно ----------------------------------------

@pytest.fixture
def committed(engine) -> Iterator[dict]:
    """Отклик реального кандидата, зафиксированный commit (параллельные транзакции его видят)."""
    code = f"race-{uuid.uuid4().hex[:8]}"
    with Session(engine) as session:
        app_row = application(session, code)
        ids = {"application_id": app_row.id, "candidate_id": app_row.candidate_id,
               "position_id": f.position(session).id,
               "document_id": session.get(Candidate, app_row.candidate_id).source_document_id}
        session.commit()
    yield ids
    with Session(engine) as session:
        session.execute(delete(Candidate).where(Candidate.id == ids["candidate_id"]))
        session.execute(delete(SourceDocument).where(SourceDocument.id == ids["document_id"]))
        session.commit()


def _parallel(engine, requests: list) -> list:
    """Выполнить запросы одновременно, каждый в своей сессии и транзакции."""
    app = create_app()

    def own_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = own_session
    barrier = threading.Barrier(len(requests))
    results: list = [None] * len(requests)

    def run(index, method, url, body):
        with TestClient(app) as http:
            barrier.wait()
            results[index] = getattr(http, method)(url, json=body, headers=HR)

    threads = [threading.Thread(target=run, args=(i, *r)) for i, r in enumerate(requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.mark.parametrize("attempt", range(3))
def test_two_tabs_with_same_seq_give_one_transition(engine, committed, attempt):
    app_id = committed["application_id"]
    with Session(engine) as session:
        seq = workflow.last_seq(session, app_id)
    url = f"/api/v1/applications/{app_id}/stage"
    results = _parallel(engine, [
        ("post", url, {"to_stage_code": "screening", "expected_seq": seq}),
        ("post", url, {"to_stage_code": "rejected", "expected_seq": seq, "rejection_reason_code": "no_response"}),
    ])
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    loser = next(r for r in results if r.status_code == 409)
    assert error_code(loser) == "STALE_STAGE_FORM"
    with Session(engine) as session:
        assert len(repo.stage_history(session, app_id)) == 2  # new + один переход


@pytest.mark.parametrize("attempt", range(3))
def test_two_simultaneous_reserve_requests_give_one_active_entry(engine, committed, attempt):
    body = reserve_body(committed["candidate_id"], committed["position_id"])
    results = _parallel(engine, [("post", "/api/v1/reserve", body), ("post", "/api/v1/reserve", body)])
    assert sorted(r.status_code for r in results) == [200, 201], [r.text for r in results]
    assert len({r.json()["entry"]["reserve_id"] for r in results}) == 1
    with Session(engine) as session:
        active = session.scalar(select(func.count()).select_from(ReserveEntry).where(
            ReserveEntry.candidate_id == committed["candidate_id"], ReserveEntry.status == ReserveStatus.ACTIVE))
    assert active == 1


def _start_and_wait_blocked(engine, target) -> threading.Thread:
    """Запустить target в потоке и дождаться, что его запрос ждёт блокировку в PostgreSQL.

    pg_stat_activity запоминается на время транзакции, поэтому каждая проверка — новое соединение.
    """
    thread = threading.Thread(target=target)
    thread.start()
    for _ in range(200):
        with engine.connect() as probe:
            waiting = probe.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND datname = current_database()"
            )).scalar_one()
        if waiting:
            return thread
        threading.Event().wait(0.05)
    raise AssertionError("второй запрос не встал в ожидание блокировки")


def test_second_tab_waits_for_lock_then_gets_409(engine, committed):
    """Детерминированная гонка: первая транзакция держит строку отклика, вторая ждёт и после commit видит новый seq."""
    app_id = committed["application_id"]
    app = create_app()

    def own_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = own_session
    with Session(engine) as first:
        seq = workflow.last_seq(first, app_id)
        first.get(Application, app_id, with_for_update=True)
        repo.move_application(first, app_id, "screening")
        result = {}

        def second_tab():
            with TestClient(app) as http:
                result["response"] = http.post(f"/api/v1/applications/{app_id}/stage", headers=HR,
                                               json={"to_stage_code": "screening", "expected_seq": seq})

        thread = _start_and_wait_blocked(engine, second_tab)
        first.commit()
    thread.join(timeout=30)
    assert error_code(result["response"]) == "STALE_STAGE_FORM"


def test_second_reserve_insert_waits_on_unique_index_and_returns_winner(engine, committed):
    """Детерминированная гонка резерва: вставка второй транзакции ждёт индекс, получает конфликт
    и возвращает запись первой (created = False)."""
    with Session(engine) as first:
        winner, created = repo.reserve_candidate(first, candidate_id=committed["candidate_id"],
                                                 position_id=committed["position_id"], **BASIS)
        assert created is True
        result = {}

        def second():
            with Session(engine) as session:
                entry, created = repo.reserve_candidate(session, candidate_id=committed["candidate_id"],
                                                        position_id=committed["position_id"], **BASIS)
                result["value"] = (entry.id, created)
                session.commit()

        winner_id = winner.id
        thread = _start_and_wait_blocked(engine, second)
        first.commit()
    thread.join(timeout=30)
    entry_id, created = result["value"]
    assert created is False and entry_id == winner_id


def test_cross_shows_profile_changed_with_old_profile_rows(session, client):
    """Утверждена новая версия профиля: рекомендация показывает прежнюю оценку как stale/profile_changed
    со строками её собственной (прежней) версии профиля — так же, как список откликов."""
    built = build_case(session, "C1-unknown")
    new_profile_id, _ = _load_profile(session)
    f.approve(session, session.get(RequirementProfile, new_profile_id))
    [item] = client.get(f"/api/v1/candidates/{built['candidate_id']}/cross-assessments", headers=HR).json()["items"]
    assert (item["assessment_status"], item["stale_reason"]) == ("stale", "profile_changed")
    assert item["profile_id"] == str(new_profile_id)
    assert item["assessment"]["profile_id"] == str(built["profile_id"])
    assert item["assessment"]["formal_checks"]  # строки прежней версии профиля на месте
