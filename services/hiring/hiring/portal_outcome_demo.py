"""Учебный проход candidate-portal 5C через HTTP: запрос → прочтение → итог со следующим шагом;
отдельно «нет открытой вакансии»; чужая учётка не видит сообщения; отзыв переданного обращения.

    uv run python -m hiring.portal_outcome_demo [--base-url http://127.0.0.1:8103]"""
import argparse
import sys

from hiring.portal_clarification_demo import APPLICATION, LEGACY_B
from hiring.portal_demo import ECONOMIST, Client


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hiring.portal_outcome_demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8103")
    api = Client(parser.parse_args(argv).base_url)

    def act(login, row, action, **body):
        return api.call(login, "POST", f"/candidate-requests/{row['id']}/{action}",
                        json={"expected_revision": row["revision"]} | body).json()

    def new_request(login, message):
        row = api.call(login, "POST", "/candidate-requests", json={
            "message": message, "contact": {"channel": "email", "value": f"{login}@example.test"}}).json()
        return act(login, row, "submit")

    row = new_request("candidate2", "Ищу работу экономиста (учебно)")
    row = act("hr", row, "information-request", public_message="Укажите опыт работы", requested_items=["опыт работы"])
    inbox = api.call("candidate2", "GET", f"/candidate-requests/{row['id']}/messages").json()["items"]
    print(f"• {row['number']}: кандидат видит «{inbox[0]['title']}», непрочитанных "
          f"{api.call('candidate2', 'GET', f'/candidate-requests/{row['id']}').json()['unread_messages']}")
    read = api.call("candidate2", "POST", f"/candidate-requests/{row['id']}/messages/{inbox[0]['id']}/read").json()
    print(f"• прочитано: read_at={read['read_at']}")
    row = api.call("candidate2", "GET", f"/candidate-requests/{row['id']}").json()
    row = act("candidate2", row, "addendum", text="Опыт 3 года в планировании (учебно)")
    row = act("candidate2", row, "choose-vacancy", vacancy_ref=ECONOMIST)
    row = act("hr", row, "ready", review_basis="Внутренняя проверка достаточности (учебно)")
    row = act("hr", row, "record-consideration", candidate_ref={"system": "legacy-hr-training", "id": LEGACY_B},
              application_ref={"system": "legacy-hr-training", "id": APPLICATION}, selected_vacancy_ref=ECONOMIST,
              identity_basis="Совпали дата рождения и e-mail (учебно)", source_reference="Учебная регистрация")
    row = act("hr", row, "public-outcome", outcome="continue",
              public_explanation="Ваше обращение передано на собеседование в отдел планирования.",
              next_action="Ожидайте приглашения в течение 10 рабочих дней",
              source_reference="Решение HR после телефонного интервью (учебно)")
    own = api.call("candidate2", "GET", f"/candidate-requests/{row['id']}").json()
    print(f"• итог: {own['status']}, «{own['outcomes'][0]['public_explanation']}», шаг: {own['outcomes'][0]['next_action']}")
    print(f"• источник решения кандидату не показан: {'source_reference' not in own['outcomes'][0]}")
    other = api.call("candidate", "GET", f"/candidate-requests/{row['id']}/messages")
    print(f"• другая учётка читает сообщения: {other.status_code}")

    second = new_request("candidate", "Готов рассмотреть любые вакансии (учебно)")
    second = act("hr", second, "ready", review_basis="Сведений достаточно")
    second = act("hr", second, "public-outcome", outcome="no_open_opportunity",
                 public_explanation="Сейчас нет открытой вакансии по вашему профилю. Это не оценка ваших требований.",
                 source_reference="Проверка открытых вакансий (учебно)")
    message = api.call("candidate", "GET", f"/candidate-requests/{second['id']}/messages").json()["items"][0]
    print(f"• {second['number']}: {second['status']}, «{message['title']}» — отдельно от отказа (declined)")

    third = new_request("candidate", "Ещё одно обращение (учебно)")
    third = act("hr", third, "ready", review_basis="ok")
    gone = act("candidate", third, "withdraw", reason="Нашёл другую работу (учебно)")
    print(f"• отзыв {gone['number']}: {gone['status']} — {gone['withdrawal']['notice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
