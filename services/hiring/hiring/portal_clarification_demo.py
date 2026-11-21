"""Учебный проход candidate-portal 5B через HTTP: запрос сведений → дополнение → выбор вакансии →
ready → ручная регистрация рассмотрения.

    uv run python -m hiring.portal_clarification_demo [--base-url http://127.0.0.1:8103]

Ссылки на запись и отклик подбора — явно учебные (system=legacy-hr-training), реального соединения
с подбором нет. Две учебные записи с одинаковым ФИО: HR выбирает одну по основанию; кандидату
ссылки и основание связи не показываются."""
import argparse
import sys

from hiring.portal_demo import ECONOMIST, Client, pdf

LEGACY_A = "00000000-0000-4000-8000-000000000d01"
LEGACY_B = "00000000-0000-4000-8000-000000000d02"
APPLICATION = "00000000-0000-4000-8000-000000000d11"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hiring.portal_clarification_demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8103")
    api = Client(parser.parse_args(argv).base_url)

    def act(login, row, action, **body):
        if action == "addendum":
            body.setdefault("information_request_ref", row["information_request_ref"])
        response = api.call(login, "POST", f"/candidate-requests/{row['id']}/{action}",
                            json={"expected_revision": row["revision"]} | body)
        return response, response.json()

    row = api.call("candidate2", "POST", "/candidate-requests", json={
        "message": "Ищу работу, вакансию не выбрал (учебно)", "contact": {"channel": "email", "value": "c2@example.test"}}).json()
    _, row = act("candidate2", row, "submit")
    print(f"• подача {row['number']}: {row['status']}, цель {row['target_question']}")

    _, row = act("hr", row, "ready", review_basis="проверка")  # ещё нет резюме — HR сначала спрашивает
    response, row = act("hr", row, "information-request", public_message="Пришлите резюме и укажите опыт",
                        requested_items=["резюме", "опыт работы"])
    print(f"• HR после ready запросил сведения: {response.status_code}, статус {row['status']}")
    seen = api.call("candidate2", "GET", f"/candidate-requests/{row['id']}").json()
    print(f"• кандидат видит запрос: {seen['information_request']['public_message']} {seen['information_request']['requested_items']}")

    resume = api.call("candidate2", "POST", f"/candidate-requests/{row['id']}/documents", data={"kind": "candidate_resume"},
                      files={"file": ("resume.pdf", pdf("c2"), "application/pdf")}).json()
    row = api.call("candidate2", "GET", f"/candidate-requests/{row['id']}").json()
    response, row = act("candidate2", row, "addendum", text="Резюме приложил, опыт 3 года (учебно)", document_ids=[resume["id"]])
    print(f"• дополнение: {response.status_code}, статус {row['status']}, дополнений {len(row['addenda'])}")

    response, row = act("candidate2", row, "choose-vacancy", vacancy_ref=ECONOMIST)
    print(f"• выбор вакансии: {response.status_code}, «{row['vacancy_conditions']['title']}» — {row['vacancy_conditions']['description']}")
    response, row = act("hr", row, "ready", review_basis="Резюме и опыт достаточны для рассмотрения (учебно)")
    print(f"• HR: ready {response.status_code}, статус {row['status']}")
    print(f"• в подборе две учебные записи с тем же ФИО: …{LEGACY_A[-3:]} и …{LEGACY_B[-3:]}; HR выбирает по основанию")
    response, row = act("hr", row, "record-consideration",
                        candidate_ref={"system": "legacy-hr-training", "id": LEGACY_B},
                        application_ref={"system": "legacy-hr-training", "id": APPLICATION},
                        selected_vacancy_ref=ECONOMIST,
                        identity_basis="Выбрана …d02: совпали дата рождения и e-mail из обращения (учебно)",
                        source_reference="Учебная регистрация отклика, без реального соединения с подбором")
    print(f"• регистрация рассмотрения: {response.status_code}, статус {row['status']}, "
          f"{row['consideration']['confirmation_method']}, запись {row['consideration']['candidate_ref']}")
    own = api.call("candidate2", "GET", f"/candidate-requests/{row['id']}").json()
    print(f"• кандидат видит: {own['consideration']}; ссылок на записи подбора нет: {LEGACY_B not in str(own)}")
    denied, _ = act("candidate2", own, "record-consideration", candidate_ref={"system": "x", "id": LEGACY_A},
                    application_ref={"system": "x", "id": APPLICATION}, selected_vacancy_ref=ECONOMIST,
                    identity_basis="сам себя", source_reference="—")
    print(f"• кандидат регистрирует рассмотрение сам: {denied.status_code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
