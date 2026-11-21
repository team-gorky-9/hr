"""Fill the demonstration stand with synthetic training records through the real APIs.

Runs on the host against the private gateway (default http://127.0.0.1:8080), standard library only,
like smoke.py. Every section first reads what exists and creates records only when its section is
still empty, so a repeated run changes nothing. All people, texts and files are synthetic.

Sections (what the jury sees afterwards):
- legacy   — two applications handed off to the department (one answered), so «Руководитель
             департамента» and the handoff block of the application card are not empty;
- hiring   — a submitted candidate request with an HR clarification (candidate cabinet + HR queue);
- students — two published practice places, one assigned student with a task;
- support  — one submitted assistance case;
- development — an employee goal shared with the manager and a proposed plan;
- requirements — the training job description and a requirements draft under department review;
- guide (only --with-model) — a phone interview guide for the best assessed application.

The CLI steps (accounts, positions, résumé corpus, requirement profiles, annual report and the
optional model assessment) are run by seed-demo.sh before this script.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid

MARK = "(учебно)"
ECONOMIST = {"system": "catalog", "id": "00000000-0000-4000-8000-000000000c01", "revision": 1}
MANAGER = "00000000-0000-4000-8000-000000000103"  # workforce actor «department»
MENTOR = MANAGER
# dept_demo of legacy: fixed id from app/db/seed.py demo_user_id("dept_demo").
DEPT_DEMO = str(uuid.uuid5(uuid.UUID("6f1b8e3a-2c4d-5e6f-8a9b-0c1d2e3f4a5b"), "dept_demo"))


class Stand:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.tokens: dict[str, str] = {}

    def call(self, method, path, *, body=None, headers=None, expect=(200, 201), form=None):
        data, hdrs = None, dict(headers or {})
        if form is not None:
            data, hdrs["Content-Type"] = multipart(*form)
        elif body is not None:
            data, hdrs["Content-Type"] = json.dumps(body).encode(), "application/json"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        if status not in expect:
            raise SystemExit(f"{method} {path}: HTTP {status} {raw[:300].decode(errors='replace')}")
        return json.loads(raw) if raw else None

    # --- identities -------------------------------------------------------------------------
    def legacy(self, login="hr_demo"):
        return {"X-User-Login": login}

    def fixture(self, login):
        return {"Authorization": f"Bearer fixture:{login}"}

    def session(self, login):
        if login not in self.tokens:
            row = self.call("POST", "/workforce/api/v1/sessions", body={"login": login, "password": "123"},
                            headers={"Idempotency-Key": str(uuid.uuid4())})
            self.tokens[login] = row["access_token"]
        return {"Authorization": f"Bearer {self.tokens[login]}", "Idempotency-Key": str(uuid.uuid4())}


def multipart(fields: dict, file: tuple[str, bytes, str]):
    boundary = uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    name, content, content_type = file
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                 f"Content-Type: {content_type}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def pdf(label: str) -> bytes:
    return b"%PDF-1.4\n% synthetic training document: " + label.encode() + b"\n%%EOF\n"


# --- sections -------------------------------------------------------------------------------

def legacy(stand: Stand) -> str:
    api, hr, dept = "/legacy/api/v1", stand.legacy(), stand.legacy("dept_demo")
    if stand.call("GET", f"{api}/handoffs?contour=training", headers=dept)["items"]:
        return "handoffs already present"
    vacancies = stand.call("GET", f"{api}/vacancies?contour=training", headers=hr)["items"]
    python = next(v for v in vacancies if v["position_code"] == "python-dev")
    rows = stand.call("GET", f"{api}/vacancies/{python['vacancy_id']}/applications?contour=training", headers=hr)
    # Ranked order (the list the HR sees): with model assessment the handoffs are the top candidates.
    ranked = sorted(rows["items"], key=lambda item: (item.get("rank_position") or 999, item["candidate_code"]))
    chosen = [item["application_id"] for item in ranked][:2]
    recipient = DEPT_DEMO
    for index, application_id in enumerate(chosen):
        history = stand.call("GET", f"{api}/applications/{application_id}/history", headers=hr)
        summary = stand.call("GET", f"{api}/applications/{application_id}/handoff-summary", headers=hr)
        moved = stand.call("POST", f"{api}/applications/{application_id}/stage", headers=hr, body={
            "to_stage_code": "sent_to_department", "expected_seq": history["last_seq"], "confirm_skip": True,
            "comment": f"Передача в департамент для собеседования {MARK}",
            "handoff": {"recipient_user_id": recipient, "channel": "cabinet",
                        "summary_revision": summary["summary_revision"], "request_id": str(uuid.uuid4())}})
        if index == 0:
            stand.call("POST", f"{api}/applications/{application_id}/feedback", headers=dept, body={
                "attempt_id": moved["handoff"]["attempt_id"], "outcome": "fit", "interview_status": "yes",
                "contact_status": "yes", "request_id": str(uuid.uuid4()),
                "comment": f"Собеседование состоялось, кандидат подходит для следующего шага {MARK}"})
    return f"handed off {len(chosen)} python-dev applications, one answered"


def guide(stand: Stand) -> str:
    """Phone interview guide for the best assessed application that is still in HR hands (uses the model)."""
    api, hr = "/legacy/api/v1", stand.legacy()
    vacancies = stand.call("GET", f"{api}/vacancies?contour=training", headers=hr)["items"]
    python = next(v for v in vacancies if v["position_code"] == "python-dev")
    rows = stand.call("GET", f"{api}/vacancies/{python['vacancy_id']}/applications?contour=training", headers=hr)
    ready = [item for item in rows["items"] if item["assessment_status"] == "ready"
             and item["current_stage_code"] != "sent_to_department"]
    if not ready:
        return "skipped: no assessed application in HR hands (run with --with-model after assessment)"
    target = sorted(ready, key=lambda item: (item.get("rank_position") or 999, item["candidate_code"]))[0]
    path = f"{api}/applications/{target['application_id']}/interview-guide"
    if "core" in (stand.call("GET", path, headers=hr, expect=(200, 404)) or {}):
        return f"guide already present for {target['candidate_code']}"
    created = stand.call("POST", path, headers=hr, body={"kind": "phone", "regenerate": False,
                                                          "request_id": str(uuid.uuid4())})
    return (f"guide for {target['candidate_code']}: {len(created['core'])} core and "
            f"{len(created['clarifications'])} clarification questions")


def hiring(stand: Stand) -> str:
    api = "/hiring/api/v1"
    queue = stand.call("GET", f"{api}/candidate-requests", headers=stand.session("hr"))
    if queue["items"]:
        return "candidate requests already present"
    row = stand.call("POST", f"{api}/candidate-requests", headers=stand.session("candidate"), body={
        "vacancy_ref": ECONOMIST, "message": f"Хочу работать экономистом в администрации {MARK}",
        "contact": {"channel": "email", "value": "candidate@example.test"}})
    resume = stand.call("POST", f"{api}/candidate-requests/{row['id']}/documents", headers=stand.session("candidate"),
                        form=({"kind": "candidate_resume"}, ("resume.pdf", pdf("resume"), "application/pdf")))
    row = stand.call("POST", f"{api}/candidate-requests/{row['id']}/submit", headers=stand.session("candidate"),
                     body={"expected_revision": resume["request_revision"]})
    stand.call("POST", f"{api}/candidate-requests/{row['id']}/information-request", headers=stand.session("hr"), body={
        "expected_revision": row["revision"],
        "public_message": "Опишите опыт работы с бюджетным планированием",
        "requested_items": ["опыт работы", "обновлённое резюме"]})
    return f"request {row['number']} submitted, clarification sent"


def students(stand: Stand) -> str:
    api, hr = "/students/api/v1/students", stand.session("hr")
    if stand.call("GET", f"{api}/opportunities", headers=hr)["items"]:
        return "practice places already present"
    places = []
    for title, description in (
        ("Практика в департаменте экономики", "Подготовка аналитических справок по исполнению бюджета"),
        ("Практика в отделе подбора кадров", "Разбор обращений кандидатов и подготовка сводок"),
    ):
        row = stand.call("POST", f"{api}/opportunities", headers=hr, body={
            "title": title, "description": f"{description} {MARK}", "starts_on": "2027-02-01",
            "ends_on": "2027-03-31", "capacity": 2, "mentor_actor_id": MENTOR})
        places.append(stand.call("POST", f"{api}/opportunities/{row['id']}/publish", headers=hr,
                                 body={"expected_revision": row["revision"]}))
    application = stand.call("POST", f"{api}/applications", headers=stand.session("candidate"), body={
        "opportunity_id": places[0]["id"], "university_label": "ННГУ им. Лобачевского (учебно)",
        "programme_label": "Экономика", "comment": "Интересна работа с муниципальным бюджетом"})
    placement = stand.call("POST", f"{api}/applications/{application['id']}/assign", headers=hr, body={
        "expected_revision": application["revision"], "confirmation_basis": f"Даты и наставник сверены {MARK}"})
    stand.call("POST", f"{api}/placements/{placement['id']}/tasks", headers=stand.session("department"), body=TASK)
    return "2 places published, one student assigned with a task"


TASK = {
    "title": "Сводка исполнения бюджета (учебно)",
    "description": "Классифицируйте 10 учебных строк расходов и объясните спорные случаи",
    "criteria": [{"key": "classification", "text": "Объясняет спорные категории", "required": True}],
}

def support(stand: Stand) -> str:
    api, employee = "/social-support/api/v1/support", stand.fixture("employee")
    if stand.call("GET", f"{api}/cases", headers=employee):
        return "assistance cases already present"
    rule = stand.call("GET", f"{api}/rules", headers=employee)[0]
    case = stand.call("POST", f"{api}/cases", headers=employee, body={
        "rule_version_id": rule["id"], "statement": f"Прошу материальную помощь в связи с рождением ребёнка {MARK}"})
    stand.call("POST", f"{api}/cases/{case['id']}/documents", headers=employee, form=(
        {"expected_revision": case["revision"], "item_key": "application"},
        ("zayavlenie.txt", "Учебное заявление без персональных данных".encode(), "text/plain")))
    case = stand.call("GET", f"{api}/cases/{case['id']}", headers=employee)
    stand.call("POST", f"{api}/cases/{case['id']}/submit", headers=employee, body={"expected_revision": case["revision"]})
    return "one assistance case submitted"


def development(stand: Stand) -> str:
    api = "/workforce/api/v1/development"
    if stand.call("GET", f"{api}/goals", headers=stand.session("employee"))["items"]:
        return "development goals already present"
    goal = stand.call("POST", f"{api}/goals", headers=stand.session("employee"), body={
        "title": "Освоить подготовку аналитических сводок", "description": f"Источник: ДИ экономиста {MARK}"})
    goal = stand.call("POST", f"{api}/goals/{goal['id']}/share", headers=stand.session("employee"),
                      body={"expected_revision": goal["revision"], "recipient_actor_id": MANAGER})
    stand.call("POST", f"{api}/plans", headers=stand.session("department"), body={
        "goal_id": goal["id"], "goal_revision": goal["revision"], "reviewer_actor_id": MANAGER,
        "title": "Проба аналитической сводки",
        "criteria": [{"key": "sources", "text": "Указаны источники", "required": True},
                     {"key": "conclusion", "text": "Обоснован вывод", "required": True}],
        "activities": [{"key": "draft", "title": "Подготовить текст сводки", "criterion_keys": ["sources"],
                        "resource_note": "Два часа рабочего времени"},
                       {"key": "summary", "title": "Сформулировать вывод", "criterion_keys": ["conclusion"],
                        "resource_note": "Час рабочего времени"}]})
    return "goal shared, plan proposed by the manager"


JOB_DESCRIPTION = """Учебная должностная инструкция экономиста.
Сотрудник составляет финансовые таблицы и проверяет исходные суммы.
Сотрудник объясняет выявленные расхождения в расчёте.
Документ создан для тестирования и не устанавливает рабочие требования организации.
"""  # = fixtures/wave-1/job-description.txt


def requirements(stand: Stand) -> str:
    """Job description of the training economist and a requirements draft sent to the department."""
    api, position = "/requirements/api/v1", "economist-training"
    if stand.call("GET", f"{api}/drafts", headers=stand.session("hr"))["items"]:
        return "requirement drafts already present"
    source = stand.call("POST", f"{api}/sources", headers=stand.session("hr"), form=(
        {"position_code": position}, ("job-description.txt", JOB_DESCRIPTION.encode(), "text/plain")))
    ref = lambda address, quote: [{"source_document_id": source["id"], "address": address, "quote": quote}]
    content = {
        "schema_version": "requirement-draft/1.0", "position_code": position, "is_synthetic": True,
        "note": f"Черновик по учебной ДИ экономиста {MARK}",
        "sources": [{"source_document_id": source["id"], "role": "job_description", "observed_revision": "1.0",
                     "is_primary": True}],
        "formal_requirements": [{
            "key": "econ.experience.relevant", "kind": "experience",
            "description": "Проверка расчётов и составление финансовых таблиц",
            "params": {"schema_version": "0.1", "scope": "relevant_role", "minimum_defined": False,
                       "relevance_hint": "составление финансовых таблиц и проверка исходных сумм"},
            "is_mandatory": True, "verification": "resume", "origin": "source",
            "source_refs": ref("абз. 2", "Сотрудник составляет финансовые таблицы и проверяет исходные суммы.")}],
        "competencies": [{
            "key": "econ.analytics", "code": "ECON-ANL", "name": "Финансовый анализ и объяснение расхождений",
            "origin": "source", "source_refs": ref("абз. 3", "Сотрудник объясняет выявленные расхождения в расчёте."),
            "indicators": [{"key": "econ.analytics.variance", "text": "Объясняет выявленные расхождения в расчёте",
                            "is_mandatory": True, "verification": "interview", "origin": "source",
                            "source_refs": ref("абз. 3", "Сотрудник объясняет выявленные расхождения в расчёте.")}]}],
    }
    draft = stand.call("POST", f"{api}/drafts", headers=stand.session("hr"),
                       body={"position_code": position, "content": content})
    stand.call("POST", f"{api}/drafts/{draft['id']}/submit", headers=stand.session("hr"),
               body={"expected_revision": draft["revision"], "reviewer_actor_id": MANAGER})
    return "job description uploaded, draft sent to the department for review"


SECTIONS = {"legacy": legacy, "hiring": hiring, "students": students, "support": support,
            "development": development, "requirements": requirements}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="http://127.0.0.1:8080")
    parser.add_argument("--only", action="append", choices=sorted(SECTIONS) + ["guide"])
    parser.add_argument("--with-model", action="store_true", help="also prepare one interview guide (model call)")
    args = parser.parse_args(argv)
    stand = Stand(args.base)
    sections = dict(SECTIONS, guide=guide) if args.with_model or "guide" in (args.only or []) else SECTIONS
    failed = 0
    for name in args.only or sections:
        try:
            print(f"{name}: {sections[name](stand)}")
        except SystemExit as error:  # one empty screen must not block the others
            failed += 1
            print(f"{name}: FAILED {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
