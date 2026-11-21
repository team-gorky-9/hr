"""HTTP гайда интервью, ответов и подтверждения требования (interview.md v0.4, §4–6; задача interview-01).

Контрольный пример §6 на учебном профиле py-9001 (стаж ≥ 24 мес., verification = resume) и FakeLLMClient:
1. py-9001 со стажем unknown → один уточняющий вопрос, ответ, подтверждение по интервью → resolved;
2. второй кандидат без пробелов → уточнений нет, вызовов модели ноль;
3. повторы, чужой вопрос, роль department, конфликт ревизии, ответ в вытесненную версию гайда;
4. документальное требование: устный ответ не подтверждает, документ — подтверждает;
5. сбой модели: прежний гайд с ответами читается.

Данные создаются настоящими функциями (assess_candidate, repository) и фиксируются session.commit():
POST гайда завершает чтение через rollback, а в тестовой сессии это откат точки сохранения.
"""
import re
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select

from app.ai import FakeLLMClient, LLMUnavailableError
from app.api import interview as interview_api
from app.api.errors import ApiError
from app.assessment.fixtures import FIXTURES_DIR, create_fixture_profile, load
from app.assessment.service import assess_candidate
from app.assessment.state import AssessmentState, AssessmentStatus
from app.db import repository as repo
from app.db.enums import (
    AnswerSource, ApplicationSource, Channel, CheckResult, DocumentKind, FileFormat, VerificationMethod,
)
from app.db.models import Assessment, Candidate, FormalCheck, InterviewAnswer, InterviewGuide, InterviewQuestion
from tests import factories as f
from tests.posting_helpers import confirm_response, posting_registry  # noqa: F401 (фикстура)
from tests.test_api import client  # noqa: F401  (фикстура)

HR = {"X-User-Login": "hr_demo"}
ADMIN = {"X-User-Login": "admin_demo"}
DEPT = {"X-User-Login": "dept_demo"}
FIXTURE = load(FIXTURES_DIR / "py-9001.json")
BASE = "Написал API-тесты для сервиса заявок."
STAZH = "Общий коммерческий опыт — 3 года."
IND = FIXTURE["profile"]["competencies"][0]["indicators"][0]["key"]
QUESTION = "С какого по какой месяц длился проект с API-тестами и в каком качестве вы в нём работали?"


# --- Подготовка данных ----------------------------------------------------------------

def guide_model(calls: list[str]):
    """Модель гайда: по одному вопросу на каждый переданный ключ (gap_ref_id или row_key)."""
    def respond(role, schema, system, user):
        calls.append(user)
        refs = re.findall(r'"(?:gap_ref_id|row_key)": "([^"]+)"', user)
        return {"items": [{"ref": r, "question": QUESTION,
                           "good_answer": "Месяц и год начала и окончания; работа по найму или договору",
                           "insufficient_answer": "«Около года», без дат"} for r in refs]}
    return respond


def fail_model(*_):
    pytest.fail("модель не должна вызываться")


@pytest.fixture
def use_llm(client):  # noqa: F811
    """Подменить клиента модели у маршрута гайда."""
    def install(llm):
        client.app.dependency_overrides[interview_api.get_llm_client] = lambda: llm
        return llm
    yield install
    client.app.dependency_overrides.pop(interview_api.get_llm_client, None)


def _candidate(session, code, text):
    document, _ = repo.add_source_document(
        session, kind=DocumentKind.RESUME, channel=Channel.HH_RU, file_format=FileFormat.TXT,
        original_path=f"Синтетика/{code}.txt", raw_text=f"{code}\n{text}")
    return repo.create_candidate(session, code=code, source_document_id=document.id, redacted_text=text,
                                 redaction_method="test", is_synthetic=True)


def assess(session, profile, candidate, *, statement=None):
    """Оценка оценщиком Ильи с учебной моделью: без statement стаж unknown и карточка сообщает пробел."""
    def respond(role, schema, system, user):
        if schema == "CandidateCard":
            return {"missing": [] if statement else ["длительность коммерческого опыта"]}
        if schema == "FormalExtraction":
            return {"statement": {"years": 3, "commercial": True, "quote": statement}} if statement else {}
        return {"indicators": [{"indicator_key": IND, "status": "confirmed", "quote": BASE}]}
    return assess_candidate(session, candidate_id=candidate.id, profile_id=profile.id, llm=FakeLLMClient(respond),
                            mode="technical", as_of="2026-11")


def training_profile(session, *, experience_verification=None):
    profile = create_fixture_profile(session, FIXTURE)
    if experience_verification:
        profile.formal_requirements[0].verification = experience_verification
        session.flush()
    f.approve(session, profile)
    return profile


def case(session, profile, code, *, statement=None):
    """Учебный отклик площадки на python-dev с актуальной оценкой. Данные фиксируются."""
    text = BASE + ("\n" + statement if statement else "")
    candidate = _candidate(session, code, text)
    assessment_id = assess(session, profile, candidate, statement=statement)
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=f.vacancy(session).id)
    confirm_response(session, application, "python-dev")  # цель отклика подтверждена в реестре публикаций
    session.commit()
    return {"candidate": candidate, "application_id": application.id, "assessment_id": assessment_id}


def post_guide(client, application_id, *, request_id=None, regenerate=False, headers=HR, kind="phone"):  # noqa: F811
    return client.post(f"/api/v1/applications/{application_id}/interview-guide", headers=headers,
                       json={"kind": kind, "regenerate": regenerate, "request_id": str(request_id or uuid.uuid4())})


def get_guide(client, application_id, **params):  # noqa: F811
    return client.get(f"/api/v1/applications/{application_id}/interview-guide", headers=HR, params=params)


def answer(client, guide, question, text="С 03.2023 по 12.2024 по договору, писал API-тесты", *,  # noqa: F811
           expected_revision=0, request_id=None, headers=HR, source="phone"):
    return client.post(
        f"/api/v1/interviews/{guide['interview_id']}/questions/{question['question_id']}/answers", headers=headers,
        json={"text": text, "source": source, "expected_revision": expected_revision,
              "request_id": str(request_id or uuid.uuid4())})


def confirm(client, assessment_id, requirement_id, *, basis, answer_id=None, request_id=None,  # noqa: F811
            result="met", comment="Подтверждено на звонке"):
    return client.post(
        f"/api/v1/assessments/{assessment_id}/formal-checks/{requirement_id}/confirm", headers=HR,
        json={"result": result, "basis": basis, "comment": comment, "request_id": str(request_id or uuid.uuid4()),
              "answer_id": str(answer_id) if answer_id else None})


def code(response) -> str:
    return response.json()["error"]["code"]


def rows(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# --- §6.1 py-9001: один вопрос, ответ, подтверждение по интервью ------------------------------

def test_py9001_one_question_answer_and_interview_confirmation(session, client, use_llm):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9001")
    calls: list[str] = []
    llm = use_llm(FakeLLMClient(guide_model(calls)))
    request_id = uuid.uuid4()

    created = post_guide(client, data["application_id"], request_id=request_id)
    assert created.status_code == 201, created.text
    guide = created.json()
    assert (guide["guide_version"], guide["model_calls"], guide["is_training"]) == (1, 1, True)
    assert guide["core"] == [] and guide["uncovered_gaps"] == [] and guide["document_requests"] == []
    assert len(guide["clarifications"]) == 1
    question = guide["clarifications"][0]
    assert {s["type"] for s in question["sources"]} == {"formal_check", "card_missing"}
    assert question["status"] == "open" and question["criterion"]["good_answer"]
    assert question["gap"] and question["gap_ref_id"].startswith("gap:")
    assert BASE not in calls[0]  # текст резюме в генерацию не уходит
    assert guide["assessment_id"] == str(data["assessment_id"]) and not guide["is_stale"]
    assert len(llm.calls) == 0  # вызовы записаны в журнал и сброшены

    # Повтор того же запроса — тот же гайд и тот же статус; новый запрос без regenerate — 200 без модели.
    use_llm(FakeLLMClient(fail_model))
    replay = post_guide(client, data["application_id"], request_id=request_id)
    assert (replay.status_code, replay.json()["guide_id"]) == (201, guide["guide_id"])
    again = post_guide(client, data["application_id"])
    assert (again.status_code, again.json()["guide_id"]) == (200, guide["guide_id"])
    # regenerate без изменения основания — та же версия, модель не вызывается.
    same = post_guide(client, data["application_id"], regenerate=True)
    assert (same.status_code, same.json()["guide_version"]) == (200, 1)

    # Ответ кадровика; повтор с тем же request_id — та же запись.
    answer_request = uuid.uuid4()
    written = answer(client, guide, question, request_id=answer_request)
    assert written.status_code == 201, written.text
    body = written.json()
    assert (body["revision"], body["source"], body["author"]["login"], body["previous_answer_id"]) == (
        1, "phone", "hr_demo", None)
    replayed = answer(client, guide, question, request_id=answer_request)
    assert (replayed.status_code, replayed.json()["answer_id"]) == (200, body["answer_id"])
    assert rows(session, InterviewAnswer) == 1
    after_answer = get_guide(client, data["application_id"]).json()["clarifications"][0]
    assert after_answer["status"] == "answered" and after_answer["answer"]["answer_id"] == body["answer_id"]

    # Подтверждение стажа ответом на звонке: требование verification = resume принимает basis = interview.
    requirement_id = next(s["requirement_id"] for s in question["sources"] if s["type"] == "formal_check")
    confirm_request = uuid.uuid4()
    confirmed = confirm(client, data["assessment_id"], requirement_id, basis="interview",
                        answer_id=body["answer_id"], request_id=confirm_request)
    assert confirmed.status_code == 201, confirmed.text
    new_version = confirmed.json()
    check = next(c for c in new_version["formal_checks"] if c["requirement_id"] == requirement_id)
    assert (check["result"], check["basis"], check["is_preliminary"]) == ("met", "interview", False)
    assert new_version["version"] == 2
    stored = session.get(Assessment, uuid.UUID(new_version["assessment_id"]))
    assert stored.base_assessment_id == data["assessment_id"]
    row = next(c for c in stored.formal_checks if str(c.requirement_id) == requirement_id)
    assert str(row.source_answer_id) == body["answer_id"]
    # Повтор подтверждения — та же версия, второй не появилось.
    replay_confirm = confirm(client, data["assessment_id"], requirement_id, basis="interview",
                             answer_id=body["answer_id"], request_id=confirm_request)
    assert (replay_confirm.status_code, replay_confirm.json()["assessment_id"]) == (200, new_version["assessment_id"])
    assert session.scalar(select(func.count()).select_from(Assessment)
                          .where(Assessment.candidate_id == data["candidate"].id)) == 2

    # Гайд не устарел (базовая оценка та же), вопрос закрыт подтверждением.
    final = get_guide(client, data["application_id"]).json()
    assert not final["is_stale"] and final["current_assessment_id"] == new_version["assessment_id"]
    resolved = final["clarifications"][0]
    assert resolved["status"] == "resolved"
    assert (resolved["resolved_by"]["basis"], resolved["resolved_by"]["confirmed_by"]["login"]) == (
        "interview", "hr_demo")


# --- §6.2 второй кандидат без пробелов --------------------------------------------------------

def test_candidate_without_gaps_gets_no_clarifications_and_no_model_calls(session, client, use_llm):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9002", statement=STAZH)
    use_llm(FakeLLMClient(fail_model))
    response = post_guide(client, data["application_id"])
    assert response.status_code == 201, response.text
    guide = response.json()
    assert (guide["clarifications"], guide["core"], guide["model_calls"]) == ([], [], 0)


def test_core_rubric_is_generated_once_and_shared(session, client, use_llm):  # noqa: F811
    """Ядро — одно на версию профиля: второй кандидат получает те же вопросы без вызова модели."""
    profile = create_fixture_profile(session, FIXTURE)
    indicator = profile.competencies[0].indicators[0]
    indicator.check_stage, indicator.verification = "interview", "interview"
    session.flush()
    f.approve(session, profile)
    first = case(session, profile, "py-9010", statement=STAZH)
    second = case(session, profile, "py-9011", statement=STAZH)

    calls: list[str] = []
    use_llm(FakeLLMClient(guide_model(calls)))
    g1 = post_guide(client, first["application_id"]).json()
    assert len(calls) == 1 and len(g1["core"]) == 1 and g1["rubric_status"] == "draft"
    use_llm(FakeLLMClient(fail_model))
    g2 = post_guide(client, second["application_id"]).json()
    strip = lambda items: [(q["question"], q["criterion"], q["rubric_question_id"]) for q in items]  # noqa: E731
    assert strip(g1["core"]) == strip(g2["core"]) and g2["model_calls"] == 0
    assert g1["core"][0]["sources"][0]["type"] == "profile_row" and g1["core"][0]["status"] == "open"


# --- §6.3 ответы: повторы, права, конфликты, вытесненная версия ---------------------------------

def test_answer_rules_reject_before_write(session, client, use_llm):  # noqa: F811
    profile = training_profile(session)
    first = case(session, profile, "py-9020")
    other = case(session, profile, "py-9021")
    use_llm(FakeLLMClient(guide_model([])))
    guide = post_guide(client, first["application_id"]).json()
    foreign = post_guide(client, other["application_id"]).json()
    question = guide["clarifications"][0]

    # Вопрос чужого отклика по маршруту этой встречи и роль department — отказ, строк нет.
    stranger = answer(client, guide, foreign["clarifications"][0])
    assert (stranger.status_code, code(stranger)) == (404, "QUESTION_NOT_FOUND")
    forbidden = answer(client, guide, question, headers=DEPT)
    assert (forbidden.status_code, code(forbidden)) == (403, "FORBIDDEN_ROLE")
    for path in ("guide", "list"):
        response = (post_guide(client, first["application_id"], headers=DEPT) if path == "guide"
                    else client.get(f"/api/v1/applications/{first['application_id']}/interview-guide", headers=DEPT))
        assert (response.status_code, code(response)) == (403, "FORBIDDEN_ROLE")
    no_user = client.get(f"/api/v1/applications/{first['application_id']}/interview-guide")
    assert (no_user.status_code, code(no_user)) == (401, "USER_REQUIRED")
    assert rows(session, InterviewAnswer) == 0

    # Первый ответ принят; правка по устаревшей ревизии — конфликт, сохранён первый ответ с автором.
    accepted = answer(client, guide, question, "С 03.2023 по 12.2024")
    assert accepted.status_code == 201
    stale = answer(client, guide, question, "Около года", headers=ADMIN)
    assert (stale.status_code, code(stale)) == (409, "REVISION_CONFLICT")
    assert stale.json()["error"]["details"]["current_revision"] == 1
    fixed = answer(client, guide, question, "С 03.2023 по 12.2024 по договору", expected_revision=1, headers=ADMIN)
    assert fixed.status_code == 201 and fixed.json()["previous_answer_id"] == accepted.json()["answer_id"]
    history = client.get(f"/api/v1/interviews/{guide['interview_id']}/questions/{question['question_id']}/answers",
                         headers=HR).json()["items"]
    assert [(a["revision"], a["author"]["login"]) for a in history] == [(1, "hr_demo"), (2, "admin_demo")]

    # Тот же request_id с другим текстом — ключ занят.
    reused = answer(client, guide, question, "другой текст", expected_revision=2,
                    request_id=session.scalar(select(InterviewAnswer.request_id).where(InterviewAnswer.revision == 1)))
    assert (reused.status_code, code(reused)) == (409, "REQUEST_ID_REUSED")
    empty = answer(client, guide, question, "   ", expected_revision=2)
    assert empty.status_code == 422
    assert rows(session, InterviewAnswer) == 2


def test_regenerate_after_reassessment_supersedes_and_carries_answer(session, client, use_llm):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9030")
    use_llm(FakeLLMClient(guide_model([])))
    v1 = post_guide(client, data["application_id"]).json()
    old_question = v1["clarifications"][0]
    old_answer = answer(client, v1, old_question).json()

    # Резюме переоценили (новая базовая оценка), стаж всё ещё unknown.
    assess(session, profile, data["candidate"])
    session.commit()
    assert get_guide(client, data["application_id"]).json()["stale_reason"] == "assessment_changed"
    regenerated = post_guide(client, data["application_id"], regenerate=True)
    assert regenerated.status_code == 201, regenerated.text
    v2 = regenerated.json()
    assert v2["guide_version"] == 2 and v2["interview_id"] == v1["interview_id"] and not v2["is_stale"]
    carried = v2["clarifications"][0]
    assert carried["gap_ref_id"] == old_question["gap_ref_id"]
    assert carried["carried_from_question_id"] == old_question["question_id"]
    assert carried["answer"]["answer_id"] == old_answer["answer_id"] and carried["answer"]["carried_over"]
    assert carried["status"] == "answered"

    # Ответ в вытесненную версию — 409; правка перенесённого — первая ревизия нового вопроса.
    superseded = answer(client, v1, old_question, "уточнение", expected_revision=1)
    assert (superseded.status_code, code(superseded)) == (409, "GUIDE_SUPERSEDED")
    assert superseded.json()["error"]["details"]["guide_version"] == 2
    edited = answer(client, v2, carried, "С 03.2023 по 12.2024 по договору").json()
    assert (edited["revision"], edited["previous_answer_id"]) == (1, old_answer["answer_id"])
    # Старая версия читается по номеру вместе со своим ответом.
    old = get_guide(client, data["application_id"], guide_version=1).json()
    assert old["clarifications"][0]["answer"]["answer_id"] == old_answer["answer_id"] and old["is_stale"]


# --- §6.4 документальное требование -------------------------------------------------------------

def test_document_requirement_needs_documents_not_oral_answer(session, client, use_llm):  # noqa: F811
    """Стаж в этом варианте профиля подтверждается документом: по резюме вывод предварительный."""
    profile = training_profile(session, experience_verification="documents")
    data = case(session, profile, "py-9040", statement=STAZH)
    use_llm(FakeLLMClient(guide_model([])))
    guide = post_guide(client, data["application_id"]).json()
    request = guide["document_requests"]
    assert len(request) == 1 and guide["clarifications"] == []
    requirement_id = request[0]["requirement_id"]

    oral = confirm(client, data["assessment_id"], requirement_id, basis="interview")
    assert (oral.status_code, code(oral)) == (409, "BASIS_NOT_ALLOWED")
    assert oral.json()["error"]["details"] == {"verification": "documents", "allowed_bases": ["documents"]}
    assert get_guide(client, data["application_id"]).json()["document_requests"] == request

    by_document = confirm(client, data["assessment_id"], requirement_id, basis="documents",
                          comment="Трудовая книжка сверена")
    assert by_document.status_code == 201, by_document.text
    checked = next(c for c in by_document.json()["formal_checks"] if c["requirement_id"] == requirement_id)
    assert (checked["basis"], checked["is_preliminary"]) == ("documents", False)
    after = get_guide(client, data["application_id"]).json()
    assert after["document_requests"] == [] and not after["is_stale"]
    # Прежняя версия оценки читается.
    assert session.get(Assessment, data["assessment_id"]).is_current is False


def test_confirm_rules(session, client, use_llm):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9050")
    other = case(session, profile, "py-9051")
    use_llm(FakeLLMClient(guide_model([])))
    guide = post_guide(client, data["application_id"]).json()
    foreign_guide = post_guide(client, other["application_id"]).json()
    question = guide["clarifications"][0]
    requirement_id = next(s["requirement_id"] for s in question["sources"] if s["type"] == "formal_check")
    foreign_answer = answer(client, foreign_guide, foreign_guide["clarifications"][0]).json()

    missing = confirm(client, data["assessment_id"], requirement_id, basis="interview")
    assert (missing.status_code, code(missing)) == (409, "ANSWER_REQUIRED")
    foreign = confirm(client, data["assessment_id"], requirement_id, basis="interview",
                      answer_id=foreign_answer["answer_id"])
    assert (foreign.status_code, code(foreign)) == (409, "ANSWER_NOT_FOR_REQUIREMENT")
    resume = client.post(f"/api/v1/assessments/{data['assessment_id']}/formal-checks/{requirement_id}/confirm",
                         headers=HR, json={"result": "met", "basis": "resume", "comment": "x",
                                           "request_id": str(uuid.uuid4())})
    assert resume.status_code == 422
    dept = client.post(f"/api/v1/assessments/{data['assessment_id']}/formal-checks/{requirement_id}/confirm",
                       headers=DEPT, json={"result": "met", "basis": "documents", "comment": "x",
                                           "request_id": str(uuid.uuid4())})
    assert (dept.status_code, code(dept)) == (403, "FORBIDDEN_ROLE")

    first = confirm(client, data["assessment_id"], requirement_id, basis="documents")
    assert first.status_code == 201
    old = confirm(client, data["assessment_id"], requirement_id, basis="documents")
    assert (old.status_code, code(old)) == (409, "ASSESSMENT_NOT_CURRENT")
    assert old.json()["error"]["details"]["current_assessment_id"] == first.json()["assessment_id"]
    unknown = confirm(client, uuid.uuid4(), requirement_id, basis="documents")
    assert (unknown.status_code, code(unknown)) == (404, "ASSESSMENT_NOT_FOUND")


# --- §6.5 сбой модели и ошибки формирования ------------------------------------------------------

def test_model_failure_keeps_previous_guide(session, client, use_llm):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9060")
    use_llm(FakeLLMClient(guide_model([])))
    v1 = post_guide(client, data["application_id"]).json()
    answer(client, v1, v1["clarifications"][0])
    assess(session, profile, data["candidate"])
    session.commit()

    use_llm(FakeLLMClient(lambda *a: LLMUnavailableError("таймаут")))
    failed = post_guide(client, data["application_id"], regenerate=True)
    assert (failed.status_code, code(failed)) == (503, "LLM_UNAVAILABLE")
    kept = get_guide(client, data["application_id"]).json()
    assert kept["guide_version"] == 1 and kept["clarifications"][0]["answer"] is not None
    assert rows(session, InterviewGuide) == 1


def test_guide_errors(session, client, use_llm):  # noqa: F811
    use_llm(FakeLLMClient(fail_model))
    profile = training_profile(session)
    candidate = _candidate(session, "py-9070", BASE)
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=f.vacancy(session).id)
    # Цель второго отклика в реестре публикаций не подтверждена — гайда нет, как и оценки в карточке.
    unresolved = repo.create_application(session, candidate_id=_candidate(session, "py-9071", BASE).id,
                                         source=ApplicationSource.RESPONSE, vacancy_id=f.vacancy(session).id,
                                         posting_title="Неизвестная публикация")
    confirm_response(session, application, "python-dev")
    session.commit()
    mapping = post_guide(client, unresolved.id)
    assert (mapping.status_code, code(mapping)) == (409, "MAPPING_REQUIRED")
    assert mapping.json()["error"]["details"]["resolution_reason"] == "missing_context"
    assert "ещё не сопоставлена" in mapping.json()["error"]["message"]
    not_assessed = post_guide(client, application.id)
    assert (not_assessed.status_code, code(not_assessed)) == (409, "ASSESSMENT_REQUIRED")
    absent = get_guide(client, application.id)
    assert (absent.status_code, code(absent)) == (404, "GUIDE_NOT_FOUND")
    unknown = post_guide(client, uuid.uuid4())
    assert (unknown.status_code, code(unknown)) == (404, "APPLICATION_NOT_FOUND")
    history = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.HISTORY,
                                      external_position_title="Старая должность")
    session.commit()
    outside = post_guide(client, history.id)
    assert (outside.status_code, code(outside)) == (409, "NOT_WORKING_APPLICATION")
    assert profile.id  # профиль утверждён, но оценки нет — отличие от NO_APPROVED_PROFILE


@pytest.mark.parametrize(
    ("status", "resolution_reason", "expected_code", "expected_message"),
    [
        (AssessmentStatus.MAPPING_REQUIRED, "unknown_publication", "MAPPING_REQUIRED", "ещё не сопоставлена"),
        (AssessmentStatus.NOT_APPLICABLE, "no_matching_position", "NOT_APPLICABLE", "неприменим"),
    ],
)
def test_guide_distinguishes_unresolved_publication_from_inapplicable_profile(
    status, resolution_reason, expected_code, expected_message,
):
    context = SimpleNamespace(
        state=AssessmentState(status),
        resolution=SimpleNamespace(reason=resolution_reason, mapping=SimpleNamespace(explanation="Нужна сверка.")),
    )
    with pytest.raises(ApiError) as result:
        interview_api.require_ready_assessment(context)
    assert (result.value.status_code, result.value.code) == (409, expected_code)
    assert expected_message in result.value.message
    assert result.value.details["resolution_reason"] == resolution_reason


def test_guide_gate_returns_current_assessment_for_resolved_application():
    assessment = Assessment()
    context = SimpleNamespace(state=AssessmentState(AssessmentStatus.READY, assessment))
    assert interview_api.require_ready_assessment(context) is assessment


def test_stand_without_model_key_answers_409_and_503_not_500(session, client, monkeypatch):  # noqa: F811
    """Настоящая зависимость маршрута, ключа модели нет (как на стенде без YANDEX_API_KEY).

    Раньше клиент собирался в зависимости FastAPI и любой POST гайда давал 500 INTERNAL_ERROR."""
    from app.ai.client import build_client
    from app.ai.config import LLMConfig
    no_key = LLMConfig(_env_file=None, llm_provider="yandexgpt", yandex_api_key=None)
    monkeypatch.setattr(interview_api, "build_client", lambda: build_client(no_key))
    client.app.dependency_overrides.pop(interview_api.get_llm_client, None)
    profile = training_profile(session)
    candidate = _candidate(session, "py-9072", BASE)
    application = repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.RESPONSE,
                                          vacancy_id=f.vacancy(session).id)
    confirm_response(session, application, "python-dev")
    session.commit()
    not_assessed = post_guide(client, application.id)
    assert (not_assessed.status_code, code(not_assessed)) == (409, "ASSESSMENT_REQUIRED")
    ready = case(session, profile, "py-9073")
    no_model = post_guide(client, ready["application_id"])
    assert (no_model.status_code, code(no_model)) == (503, "LLM_UNAVAILABLE")
    assert rows(session, InterviewGuide) == 0


# --- Хранение -----------------------------------------------------------------------------------

def test_open_interview_is_one_per_application_and_kind(session, posting_registry):  # noqa: F811
    profile = training_profile(session)
    data = case(session, profile, "py-9080")
    first = repo.open_interview(session, data["application_id"], "phone")
    second = repo.open_interview(session, data["application_id"], "phone")
    department = repo.open_interview(session, data["application_id"], "department")
    assert first.id == second.id != department.id


@pytest.mark.parametrize(("verification", "basis", "preliminary"), [
    ("resume", "resume", False),
    ("resume", "interview", False),
    ("resume", "documents", False),
    ("documents", "resume", True),
    ("documents", "interview", True),
    ("documents", "documents", False),
    ("interview", "resume", True),
    ("interview", "interview", False),
    ("test", "resume", True),
    ("test", "test", False),
])
def test_preliminary_matrix(verification, basis, preliminary):
    assert repo.is_preliminary(CheckResult.MET, basis, verification) is preliminary
    assert repo.is_preliminary(CheckResult.UNKNOWN, basis, verification) is False


def test_deleting_candidate_removes_answers_referenced_by_confirmation(session, client, use_llm):  # noqa: F811
    """source_answer_id — NO ACTION: удаление кандидата целиком (оценки и отклики каскадом) проходит,
    а удалить отдельно ответ, на который опирается подтверждение, нельзя."""
    from sqlalchemy.exc import IntegrityError

    profile = training_profile(session)
    data = case(session, profile, "py-9090")
    use_llm(FakeLLMClient(guide_model([])))
    guide = post_guide(client, data["application_id"]).json()
    question = guide["clarifications"][0]
    written = answer(client, guide, question).json()
    requirement_id = next(s["requirement_id"] for s in question["sources"] if s["type"] == "formal_check")
    assert confirm(client, data["assessment_id"], requirement_id, basis="interview",
                   answer_id=written["answer_id"]).status_code == 201

    with pytest.raises(IntegrityError, match="fk_formal_checks_source_answer_id_interview_answers"):
        with session.begin_nested():
            session.execute(delete(InterviewAnswer).where(InterviewAnswer.id == uuid.UUID(written["answer_id"])))
    session.execute(delete(Candidate).where(Candidate.id == data["candidate"].id))
    session.flush()
    assert rows(session, InterviewAnswer) == 0 and rows(session, InterviewQuestion) == 0
    assert session.scalar(select(func.count()).select_from(FormalCheck)
                          .where(FormalCheck.source_answer_id.is_not(None))) == 0
