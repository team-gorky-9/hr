from workforce.onboarding.models import Template


def seed_templates(session):
    if session.get(Template, ("intro-v1", 1)) is not None:
        return
    session.add(
        Template(
            code="intro-v1",
            version=1,
            title="Учебная вводная программа",
            steps=[
                {
                    "key": "introduction",
                    "title": "Прочитать вводный материал",
                    "description": "Учебный материал: познакомьтесь с задачами подразделения. "
                    "Уточните у руководителя свою первую задачу и ожидаемый результат.",
                    "material_url": None,
                    "kind": "acknowledgement",
                },
                {
                    "key": "contacts",
                    "title": "Ознакомиться с контактами и порядком работы",
                    "description": "Учебный материал: кадровые вопросы адресуйте HR, рабочие — руководителю. "
                    "Запросите у них актуальные контакты, график и порядок получения доступа.",
                    "material_url": None,
                    "kind": "acknowledgement",
                },
                {
                    "key": "first-day",
                    "title": "Ознакомиться с планом первого дня",
                    "description": "Учебный план: встретиться с руководителем, познакомиться с коллегами, "
                    "проверить доступы и согласовать первую задачу. Отметка означает только ознакомление.",
                    "material_url": None,
                    "kind": "acknowledgement",
                },
            ],
        )
    )
