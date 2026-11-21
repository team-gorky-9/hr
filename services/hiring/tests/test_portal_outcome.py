"""candidate-portal 5C: публичный исход, сообщения кабинета, отзыв обращения."""
from tests.test_portal import PATH, create, submit
from tests.test_portal_clarification import consideration, post, submitted_without_target

INTERNAL = "Отзыв департамента: слабый Excel, оценка 41 балл"


def forwarded(api):
    row = submitted_without_target(api)
    row = post(api, "candidate2", row, "choose-vacancy", vacancy_ref={
        "system": "catalog", "id": "00000000-0000-4000-8000-000000000c01", "revision": 1}).json()
    row = post(api, "hr", row, "ready", review_basis=INTERNAL).json()
    return post(api, "hr", row, "record-consideration", **consideration()).json()


def messages(api, login, row):
    return api.get(login, f"{PATH}/{row['id']}/messages")


def test_request_then_outcome_and_read_mark(api):
    row = submitted_without_target(api)
    row = post(api, "hr", row, "information-request", public_message="Пришлите резюме",
               requested_items=["резюме"]).json()
    [asked] = messages(api, "candidate2", row).json()["items"]
    assert (asked["kind"], asked["read_at"]) == ("information_request", None)
    assert api.get("candidate2", f"{PATH}/{row['id']}").json()["unread_messages"] == 1
    read = api.post("candidate2", f"{PATH}/{row['id']}/messages/{asked['id']}/read", {})
    assert read.status_code == 200 and read.json()["read_at"]
    again = api.post("candidate2", f"{PATH}/{row['id']}/messages/{asked['id']}/read", {}).json()
    assert again["read_at"] == read.json()["read_at"]  # повтор не сдвигает отметку
    assert api.get("candidate2", f"{PATH}/{row['id']}").json()["unread_messages"] == 0

    row = post(api, "candidate2", api.get("candidate2", f"{PATH}/{row['id']}").json(), "addendum",
               text="Опыт 3 года, резюме пришлю отдельно").json()
    row = post(api, "candidate2", row, "choose-vacancy", vacancy_ref={
        "system": "catalog", "id": "00000000-0000-4000-8000-000000000c01", "revision": 1}).json()
    row = post(api, "hr", row, "ready", review_basis=INTERNAL).json()
    row = post(api, "hr", row, "record-consideration", **consideration()).json()
    published = post(api, "hr", row, "public-outcome", outcome="continue",
                     public_explanation="Ваше обращение передано на собеседование в отдел.",
                     next_action="Ожидайте приглашения на собеседование в течение 10 рабочих дней",
                     source_reference="Решение HR по итогам телефонного интервью (учебно)")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "forwarded"
    own = api.get("candidate2", f"{PATH}/{row['id']}").json()
    assert own["outcomes"] == [{k: published.json()["outcomes"][0][k] for k in
                                ("outcome", "public_explanation", "next_action", "decided_at")}]
    assert INTERNAL not in str(own) and "телефонного интервью" not in str(own)  # внутреннее не копируется
    titles = [m["title"] for m in messages(api, "candidate2", row).json()["items"]]
    assert titles == ["Нужны дополнительные сведения", "Рассмотрение продолжается"]
    # Другая учётка не получает сообщения и не ставит отметку; HR читает, но не отмечает прочтение.
    assert messages(api, "candidate", row).status_code == 404
    outcome_message = messages(api, "candidate2", row).json()["items"][-1]
    assert api.post("candidate", f"{PATH}/{row['id']}/messages/{outcome_message['id']}/read", {}).status_code == 404
    assert api.post("hr", f"{PATH}/{row['id']}/messages/{outcome_message['id']}/read", {}).status_code == 403
    assert messages(api, "hr", row).status_code == 200

    final = post(api, "hr", api.get("hr", f"{PATH}/{row['id']}").json(), "public-outcome", outcome="completed",
                 public_explanation="Рассмотрение завершено, спасибо за обращение.", source_reference="Итог HR")
    assert final.json()["status"] == "closed" and len(final.json()["outcomes"]) == 2


def test_no_open_opportunity_is_not_a_decline(api):
    row = submitted_without_target(api)
    row = post(api, "hr", row, "ready", review_basis="Сведений достаточно").json()
    none = post(api, "hr", row, "public-outcome", outcome="no_open_opportunity",
                public_explanation="Сейчас нет открытой вакансии по вашему профилю. Это не оценка ваших требований.",
                source_reference="Проверка открытых вакансий 21.11 (учебно)").json()
    assert none["status"] == "closed" and none["outcomes"][0]["outcome"] == "no_open_opportunity"
    [message] = messages(api, "candidate2", row).json()["items"]
    assert message["title"] == "Сейчас нет подходящей открытой вакансии"

    other = create(api)
    other = post(api, "hr", submit(api, "candidate", other), "ready", review_basis="ok").json()
    declined = post(api, "hr", other, "public-outcome", outcome="declined",
                    public_explanation="Опыт не соответствует обязательным требованиям вакансии.",
                    source_reference="Решение HR").json()
    assert declined["outcomes"][0]["outcome"] == "declined"
    assert messages(api, "candidate", other).json()["items"][0]["title"] == "Решение по обращению"


def test_outcome_and_withdrawal_rules(api):
    row = submitted_without_target(api)
    early = post(api, "hr", row, "public-outcome", outcome="declined", public_explanation="рано",
                 source_reference="—")
    assert early.json()["error"]["code"] == "INVALID_STATE"
    ready = post(api, "hr", row, "ready", review_basis="ok").json()
    no_registration = post(api, "hr", ready, "public-outcome", outcome="continue", public_explanation="продолжаем",
                           next_action="ждите", source_reference="—")
    assert no_registration.json()["error"]["code"] == "INVALID_STATE"
    assert post(api, "hr", ready, "public-outcome", outcome="continue", public_explanation="без шага",
                source_reference="—").status_code == 422
    assert post(api, "candidate2", ready, "public-outcome", outcome="completed", public_explanation="сам",
                source_reference="—").status_code == 403

    sent = forwarded(api)
    assert post(api, "hr", sent, "withdraw", reason="за кандидата").status_code == 403
    gone = post(api, "candidate2", sent, "withdraw", reason="Нашёл другую работу")
    assert gone.status_code == 200, gone.text
    body = gone.json()
    assert body["status"] == "withdrawn" and "завершает его владелец" in body["withdrawal"]["notice"]
    assert api.get("hr", f"{PATH}/{sent['id']}").json()["withdrawal"]["external_consideration_open"] is True
    after = post(api, "hr", body, "public-outcome", outcome="completed", public_explanation="поздно",
                 source_reference="—")
    assert after.json()["error"]["code"] == "INVALID_STATE"
    assert post(api, "candidate2", body, "withdraw", reason="ещё раз").json()["error"]["code"] == "INVALID_STATE"
