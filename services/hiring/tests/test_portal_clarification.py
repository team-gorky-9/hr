"""candidate-portal 5B: уточнение сведений, выбор вакансии, готовность и ручная регистрация рассмотрения."""
import uuid

from tests.test_portal import CLOSED, ECONOMIST, PATH, create, submit, upload

LEGACY_A = "00000000-0000-4000-8000-000000000d01"  # две учебные записи legacy с одинаковым именем
LEGACY_B = "00000000-0000-4000-8000-000000000d02"
APPLICATION = "00000000-0000-4000-8000-000000000d11"


def post(api, login, row, action, **body):
    if action == "addendum" and row.get("information_request_ref"):
        body.setdefault("information_request_ref", row["information_request_ref"])
    return api.post(login, f"{PATH}/{row['id']}/{action}", {"expected_revision": row["revision"]} | body)


def consideration(**changes):
    return {"candidate_ref": {"system": "legacy-hr-training", "id": LEGACY_B},
            "application_ref": {"system": "legacy-hr-training", "id": APPLICATION},
            "selected_vacancy_ref": ECONOMIST,
            "identity_basis": "Из двух записей с тем же ФИО выбрана …d02: совпали дата рождения и e-mail из обращения (учебно)",
            "source_reference": "Учебная регистрация отклика в подборе, без реального соединения"} | changes


def submitted_without_target(api):
    row = create(api, "candidate2", message="Ищу работу, вакансию не выбрал (учебно)")
    return submit(api, "candidate2", row)


def test_full_clarification_path(api):
    row = submitted_without_target(api)
    asked = post(api, "hr", row, "information-request", public_message="Пришлите резюме и укажите опыт",
                 requested_items=["резюме", "опыт работы"])
    assert asked.status_code == 200, asked.text
    row = asked.json()
    assert row["status"] == "needs_information"
    seen = api.get("candidate2", f"{PATH}/{row['id']}").json()
    assert seen["information_request"]["requested_items"] == ["резюме", "опыт работы"]
    assert "requested_by_actor_id" not in seen["information_request"]

    resume = upload(api, "candidate2", row["id"]).json()
    row = api.get("candidate2", f"{PATH}/{row['id']}").json()
    added = post(api, "candidate2", row, "addendum", text="Резюме приложил, опыт 3 года", document_ids=[resume["id"]])
    assert added.status_code == 200, added.text
    row = added.json()
    assert row["status"] == "submitted" and row["addenda"][0]["document_ids"] == [resume["id"]]
    assert row["information_request"]["answered"] is True

    chosen = post(api, "candidate2", row, "choose-vacancy", vacancy_ref=ECONOMIST)
    assert chosen.status_code == 200, chosen.text
    row = chosen.json()
    assert row["target_question"] is None and row["vacancy_conditions"]["description"].startswith("Учебное объявление")

    row = post(api, "hr", row, "ready", review_basis="Резюме и опыт достаточны для рассмотрения").json()
    assert row["status"] == "ready"
    assert api.get("candidate2", f"{PATH}/{row['id']}").json().get("review") is None  # основание HR — внутреннее

    recorded = post(api, "hr", row, "record-consideration", **consideration())
    assert recorded.status_code == 200, recorded.text
    hr_view = recorded.json()
    assert hr_view["status"] == "forwarded"
    assert hr_view["consideration"]["candidate_ref"]["id"] == LEGACY_B
    assert hr_view["consideration"]["confirmation_method"] == "manual-confirmed"
    own = api.get("candidate2", f"{PATH}/{row['id']}").json()
    assert own["consideration"]["status"] == "registered" and own["consideration"]["selected_vacancy"]["title"]
    assert LEGACY_A not in str(own) and LEGACY_B not in str(own) and "дата рождения" not in str(own)
    history = [e["event_type"] for e in api.get("hr", f"{PATH}/{row['id']}/history").json()["items"]]
    assert history == ["request.created", "request.submitted", "information.requested", "document.added",
                       "addendum.added", "vacancy.chosen", "request.ready", "consideration.recorded"]


def test_ready_stays_until_registration_and_roles(api):
    row = submitted_without_target(api)
    # Кандидат не выполняет действия HR, HR не пишет дополнение за кандидата.
    assert post(api, "candidate2", row, "ready", review_basis="сам себе готов").status_code == 403
    assert post(api, "candidate2", row, "information-request", public_message="?", requested_items=["x"]).status_code == 403
    assert post(api, "hr", row, "record-consideration", **consideration()).json()["error"]["code"] == "INVALID_STATE"
    ready = post(api, "hr", row, "ready", review_basis="Достаточно для рассмотрения").json()
    assert post(api, "hr", ready, "addendum", text="за кандидата").status_code == 403
    assert post(api, "candidate", ready, "choose-vacancy", vacancy_ref=ECONOMIST).status_code == 404  # чужое
    closed = post(api, "candidate2", ready, "choose-vacancy", vacancy_ref=CLOSED)
    assert (closed.status_code, closed.json()["error"]["code"]) == (409, "VACANCY_NOT_AVAILABLE")
    unknown = post(api, "hr", ready, "record-consideration",
                   **consideration(selected_vacancy_ref=ECONOMIST | {"revision": 9}))
    assert unknown.json()["error"]["code"] == "VACANCY_NOT_AVAILABLE"
    # Сосед недоступен / регистрации ещё нет — обращение остаётся ready.
    assert api.get("hr", f"{PATH}/{ready['id']}").json()["status"] == "ready"
    stale = post(api, "hr", row, "record-consideration", **consideration())
    assert stale.json()["error"]["code"] == "STALE_REVISION"
    # Повторный запрос сведений снимает готовность.
    again = post(api, "hr", ready, "information-request", public_message="Уточните дату выхода",
                 requested_items=["дата выхода"]).json()
    assert again["status"] == "needs_information" and again["review"] is None


def test_addendum_rules(api):
    row = submitted_without_target(api)
    assert post(api, "candidate2", row, "addendum", text="без запроса").json()["error"]["code"] == "INVALID_STATE"
    row = post(api, "hr", row, "information-request", public_message="Нужно резюме", requested_items=["резюме"]).json()
    foreign = create(api, "candidate")
    foreign_doc = upload(api, "candidate", foreign["id"]).json()
    wrong = post(api, "candidate2", row, "addendum", text="чужой файл", document_ids=[foreign_doc["id"]])
    assert (wrong.status_code, wrong.json()["error"]["field"]) == (422, "document_ids")
    assert post(api, "candidate2", row, "addendum", text="").status_code == 422
    assert post(api, "candidate2", row, "addendum", text="ок", document_ids=[str(uuid.uuid4())]).status_code == 422
