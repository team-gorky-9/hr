"""Curated synthetic surveys for the employee demonstration."""

import json
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from feedback.publications import publish
from feedback.schemas import CycleCreate, PublicationCreate
from feedback.store import DEMO_IDS, DEMO_ORG, new, save, seed_demo, transaction


def survey(key, title, questions, topics, status):
    return {
        "id": uuid5(NAMESPACE_URL, f"feedback-demo/survey/{key}"),
        "status": status,
        "body": CycleCreate(
            title=title,
            question_version=f"{key}-v1",
            questions=[{"key": code, "text": text, "min": 1, "max": 3} for code, text in questions],
            topic_options=[{"key": code, "label": label} for code, label in topics],
            groups=[
                {"key": "large", "label": "Учебная группа", "eligible_count": 40},
                {"key": "small", "label": "Малая учебная группа", "eligible_count": 7},
            ],
        ),
    }


DEMO_SURVEYS = (
    survey(
        "processes", "Организация работы",
        [("priorities", "Понятно ли, какую задачу выполнить в первую очередь?"),
         ("handoffs", "Удобно ли передавать задачи между подразделениями?"),
         ("workload", "Хватает ли времени на выполнение текущих задач?")],
        [("planning", "Планирование"), ("handoffs", "Передача задач"), ("workload", "Нагрузка")],
        "open",
    ),
    survey(
        "tools", "Рабочее место и инструменты",
        [("desk", "Удобно ли организовано ваше рабочее место?"),
         ("software", "Хватает ли доступных программ для повседневной работы?"),
         ("quiet", "Удаётся ли сосредоточиться, когда работа требует тишины?")],
        [("equipment", "Оборудование"), ("software", "Программы"), ("spaces", "Рабочие пространства")],
        "closed",
    ),
    survey(
        "onboarding", "Первые недели работы",
        [("materials", "Легко ли найти вводные материалы?"),
         ("help", "Понятно ли, к кому обратиться за помощью?"),
         ("feedback", "Хватает ли обратной связи по первым задачам?")],
        [("materials", "Материалы"), ("mentor", "Поддержка наставника"), ("practice", "Первые задачи")],
        "closed",
    ),
)
DEMO_SURVEY_IDS = tuple(item["id"] for item in DEMO_SURVEYS)


def get_demo_cycle(db, cycle_id: UUID):
    if cycle_id not in DEMO_SURVEY_IDS:
        return None
    row = db.execute(
        "SELECT data FROM records WHERE id=? AND kind='cycle' AND organization_id=?",
        (str(cycle_id), DEMO_ORG),
    ).fetchone()
    if row is None:
        return None
    data = json.loads(row["data"])
    return data if data.get("is_synthetic") is True and data["created_by"] == DEMO_IDS["organizer"] else None


def seed_closed_responses(db, cycle, counts):
    # The historical sample is artificial and does not consume participant codes.
    # Each scale has three safely publishable categories with distinct counts.
    distribution = [value for value, count in enumerate(counts, start=1) for _ in range(count)]
    for offset, rating in enumerate(distribution):
        answers = [{"question_key": question["key"], "value": (rating + index - 1) % 3 + 1}
                   for index, question in enumerate(cycle["questions"])]
        topic = cycle["topic_options"][rating - 1]["key"]
        db.execute("INSERT INTO responses VALUES(?,?,?,?,?)",
                   (str(uuid4()), cycle["id"], "large", json.dumps(answers), topic))


def seed_demo_surveys(path):
    seed_demo(path)
    actor = {"id": DEMO_IDS["organizer"], "organization_id": DEMO_ORG, "assignments": ["publisher"]}
    with transaction(path) as db:
        for index, item in enumerate(DEMO_SURVEYS):
            survey_id = item["id"]
            if db.execute("SELECT 1 FROM records WHERE id=?", (str(survey_id),)).fetchone():
                if get_demo_cycle(db, survey_id) is None:
                    raise ValueError(f"Training survey ID is already in use: {survey_id}")
                continue
            cycle = new(actor, **item["body"].model_dump(), status="draft", is_synthetic=True)
            cycle["id"] = str(survey_id)
            save(db, "cycle", cycle, actor, "create", True)
            cycle["status"] = "open"
            save(db, "cycle", cycle, actor, "open")
            if item["status"] == "closed":
                seed_closed_responses(db, cycle, (5 + index, 7, 10 - index))
                cycle["status"] = "closed"
                save(db, "cycle", cycle, actor, "closed")
                publish(survey_id, PublicationCreate(
                    expected_revision=cycle["revision"], policy={"k": 5}, policy_basis="Синтетический учебный пример",
                ), (db, actor))
