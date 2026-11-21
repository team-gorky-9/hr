#!/usr/bin/env python3
"""Apply the reviewed demo curation in independently repeatable sections.

Run inside the legacy container after verifying the backups. The default
prints the exact scope. Neither mode deletes records, resumes, or vacancies.
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

VERSION = "demo-curation-v1"
ORG = "00000000-0000-4000-8000-000000000001"
EMPLOYEE_ACTOR = "00000000-0000-4000-8000-000000000104"
ECONOMICS = "00000000-0000-4000-8000-000000000011"
PRACTICE = "a6f60dbf-093c-4b3f-813d-9a3e209fe8f5"
PRACTICE_REASON = "Учебная публикация с истёкшим сроком. Заявок и назначенных участий нет."
WORKFORCE = "/workforce/api/v1"
STUDENTS = "/students/api/v1/students"
ORIGIN = {"system": "manual", "id": VERSION + ":employee-104"}

# All names below are invented display names for the checked-in synthetic corpus.
DEMO_CODES = ("hr-9001", *(f"hr-{n}" for n in range(9101, 9107)),
              *(f"py-{n}" for n in range(9101, 9107)), *(f"search-{n}" for n in range(9001, 9019)))
DEMO_NAMES = dict(zip(DEMO_CODES, (
    "Мария Сергеевна Тихонова", "Ирина Андреевна Сорокина", "Ольга Романовна Громова",
    "Альбина Викторовна Бородина", "Екатерина Олеговна Крылова", "Елена Игоревна Власова",
    "Анна Денисовна Ершова", "Денис Андреевич Кондратьев", "Виктор Романович Никитин",
    "Роман Павлович Гаврилов", "Илья Николаевич Степанов", "Антон Иванович Соболев",
    "Михаил Денисович Корнеев", "Олег Артёмович Сергеев", "Вера Степановна Гусева",
    "Родион Петрович Мартынов", "Иван Денисович Волков", "Наталья Антоновна Соколова",
    "Григорий Ильич Марков", "Маргарита Романовна Осипова", "Артём Олегович Васильев",
    "Оксана Павловна Зайцева", "Алексей Ильич Воронов", "Алина Романовна Алексеева",
    "Сергей Иванович Смирнов", "Алёна Степановна Попова", "Егор Олегович Карпов",
    "Дарья Алексеевна Морозова", "Дмитрий Иванович Рябов", "Вероника Сергеевна Щукина",
    "Александра Михайловна Котова",
), strict=True))
WORKFLOW = {
    "py-9103": (UUID("099bf405-38f8-4aa5-9424-585cb9fb4b4b"), "sent_to_department"),
    "py-9104": (UUID("51537ce4-fe3d-48fc-a9ee-30003f04e78f"), "phone_interview"),
}


def training_origin(code, source):
    path = source.original_path.replace("\\", "/")
    is_search = code.startswith("search-")
    return (bool(source.import_batch) and Path(path).stem.casefold() == code and
            ("Учебный поиск/" in path if is_search else Path(path).suffix.lower() in (".txt", ".docx")))


def curate_names():
    from sqlalchemy import select

    from app.db.models import Candidate, CandidatePii, SourceDocument
    from app.db.session import SessionLocal

    changes = {"filled": [], "existing": [], "skipped": []}
    with SessionLocal.begin() as session:
        for code, name in DEMO_NAMES.items():
            row = session.execute(select(Candidate, SourceDocument)
                                  .join(SourceDocument, Candidate.source_document_id == SourceDocument.id)
                                  .where(Candidate.code == code, Candidate.is_synthetic.is_(True))
                                  .with_for_update(of=Candidate)).one_or_none()
            if row is None or not training_origin(code, row[1]):
                changes["skipped"].append(code)
                continue
            candidate = row[0]
            pii = session.get(CandidatePii, candidate.id, with_for_update=True)
            if pii is not None and (pii.full_name or "").strip():
                changes["existing"].append(code)
                continue
            if pii is None:
                pii = CandidatePii(candidate_id=candidate.id)
                session.add(pii)
            pii.full_name = name
            changes["filled"].append(code)
    return changes


def curate_workflow():
    from sqlalchemy import select

    from app.api import handoff, interview, workflow
    from app.api.errors import ApiError
    from app.api.schemas import HandoffIn, InterviewOutcomeIn, StageMoveIn
    from app.db import repository
    from app.db.enums import ApplicationSource, InterviewKind, UserRole
    from app.db.models import Application, Candidate, HandoffAttempt, Interview, Position, SourceDocument, StageEvent, User, Vacancy
    from app.db.session import SessionLocal

    result = {}
    for code, (ident, target) in WORKFLOW.items():
        marker = f"[synthetic:{VERSION}:{code}]"
        with SessionLocal() as session:
            actor = session.scalar(select(User).where(User.login == "hr_demo", User.role == UserRole.HR, User.is_active))
            recipient = session.scalar(select(User).where(User.login == "dept_demo", User.role == UserRole.DEPARTMENT, User.is_active))
            if not actor or not recipient:
                raise ValueError("Training HR or department actor unavailable")
            row = session.execute(select(Application, SourceDocument).select_from(Application)
                                  .join(Candidate, Candidate.id == Application.candidate_id)
                                  .join(SourceDocument, Candidate.source_document_id == SourceDocument.id)
                                  .join(Vacancy, Application.vacancy_id == Vacancy.id)
                                  .join(Position, Vacancy.position_id == Position.id)
                                  .where(Application.id == ident, Application.source == ApplicationSource.RESPONSE,
                                         Candidate.code == code, Candidate.is_synthetic.is_(True), Position.code == "python-dev")
                                  .with_for_update(of=Application)).one_or_none()
            if row is None or not training_origin(code, row[1]):
                result[code] = "skipped: provenance does not match"
                continue
            application = row[0]
            events = list(session.scalars(select(StageEvent).where(StageEvent.application_id == ident).order_by(StageEvent.seq)))
            interviews = list(session.scalars(select(Interview).where(Interview.application_id == ident)))
            handoffs = list(session.scalars(select(HandoffAttempt).where(HandoffAttempt.application_id == ident)))
            if application.current_stage_code == target and events and (events[-1].comment or "").startswith(marker):
                own_handoff = uuid5(NAMESPACE_URL, marker)
                complete = (any(row.request_id == own_handoff for row in handoffs) if target == "sent_to_department"
                            else any(row.held_at is not None and (row.summary or "").startswith(marker) for row in interviews))
                result[code] = "already present" if complete else "skipped: incomplete or changed history"
                continue
            if (application.current_stage_code != "new" or len(events) != 1 or events[0].from_stage_code is not None
                    or events[0].to_stage_code != "new" or events[0].comment is not None or interviews or handoffs):
                result[code] = "skipped: worked application"
                continue
            try:
                for stage in ("screening", "phone_interview"):
                    workflow.move_stage(session, ident, StageMoveIn(
                        to_stage_code=stage, expected_seq=workflow.last_seq(session, ident),
                        comment=marker + " Учебный сценарий подбора.",
                    ), actor, commit=False)
                if target == "sent_to_department":
                    summary = handoff.build_handoff_summary(session, ident)
                    workflow.move_stage(session, ident, StageMoveIn(
                        to_stage_code=target, expected_seq=workflow.last_seq(session, ident),
                        comment=marker + " Учебная передача для оценки опыта.",
                        handoff=HandoffIn(recipient_user_id=recipient.id, channel="cabinet",
                                          summary_revision=summary.summary_revision, request_id=uuid5(NAMESPACE_URL, marker)),
                    ), actor, commit=False)
                    session.commit()
                else:
                    pending = repository.open_interview(session, ident, InterviewKind.PHONE)
                    interview.record_outcome(session, pending.id, InterviewOutcomeIn(
                        expected_revision=pending.revision, result="continue", occurred_at=datetime.now(timezone.utc),
                        summary=marker + " Учебный разговор: уточнили опыт работы с Python и следующий шаг.",
                    ), actor)
                result[code] = "applied"
            except ApiError as exc:
                session.rollback()
                result[code] = f"skipped: service {exc.status_code}"
    return result


class Gateway:
    def __init__(self, base, fixture):
        self.base = base.rstrip("/")
        self.actors = json.loads(fixture.read_bytes())["actors"]
        self.tokens = {}

    def request(self, path, *, body=None, actor=None, key=None, method=None):
        headers = {"Accept": "application/json"}
        if actor:
            headers["Authorization"] = "Bearer " + self.tokens[actor]
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Idempotency-Key"] = str(uuid5(NAMESPACE_URL, VERSION + ":" + key)) if key else str(uuid4())
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request(self.base + path, data=data, headers=headers, method=method), timeout=20) as response:
                return json.loads(response.read()) if response.status != 204 else None
        except HTTPError as exc:
            # Never print response bodies, user inputs or bearer tokens.
            raise ValueError(f"{path.partition('?')[0]} returned HTTP {exc.code}") from None

    def login(self, login):
        actor = next(row for row in self.actors if row["login"] == login and row["organization_id"] == ORG)
        row = self.request(WORKFORCE + "/sessions", body={"login": login, "password": actor["password"]})
        if row["actor"]["actor_id"] != actor["actor_id"] or row["actor"]["organization_id"] != ORG:
            raise ValueError("Training actor scope mismatch")
        self.tokens[login] = row["access_token"]
        return actor["actor_id"]

    def close(self):
        for login in self.tokens:
            try:
                self.request(WORKFORCE + "/session", actor=login, method="DELETE")
            except (OSError, ValueError):
                print(f"Notice: failed to revoke the temporary {login} session")


def curate_workforce(api):
    api.login("hr")
    if api.login("employee") != EMPLOYEE_ACTOR:
        raise ValueError("Employee fixture identity changed")
    existing = api.request(WORKFORCE + "/onboarding/programs", actor="employee")["items"]
    if existing:
        return {"employee_programs": len(existing), "steps": [row["completed_count"] for row in existing], "changed": False}
    employees = api.request(WORKFORCE + "/employees?" + urlencode({"query": ORIGIN["id"]}), actor="hr")["items"]
    matches = [row for row in employees if row.get("account_actor_id") == EMPLOYEE_ACTOR and ORIGIN in row.get("source_refs", [])]
    if not matches:
        # The service's unique account/source constraints protect unrelated data.
        person = api.request(WORKFORCE + "/employees", actor="hr", key="employee", body={
            "display_name": "Кирилл Лебедев (учебный)", "account_actor_id": EMPLOYEE_ACTOR,
            "source_refs": [ORIGIN], "confirmation_basis": "Синтетическая карточка для демонстрации адаптации",
        })
    else:
        person = matches[0]
    ident = person["id"]
    detail = api.request(WORKFORCE + "/employees/" + ident, actor="hr")
    assignments = detail["assignments"]
    matching = [row for row in assignments if row.get("basis", {}).get("reference") == ORIGIN["id"]]
    if matching:
        assignment = matching[0]
    elif assignments:
        raise ValueError("Employee already has a different assignment; leaving it intact")
    else:
        moscow = timezone(timedelta(hours=3))
        today = datetime.now(moscow).date().isoformat()
        assignment = api.request(WORKFORCE + f"/employees/{ident}/assignments", actor="hr", key="assignment", body={
            "department_id": ECONOMICS, "position_code": "economist-training", "starts_on": today,
            "basis": {"reference": ORIGIN["id"], "issued_on": today},
        })
    api.request(WORKFORCE + "/onboarding/programs", actor="hr", key="onboarding", body={
        "workforce_assignment_id": assignment["id"], "template_code": "intro-v1", "template_version": 1,
    })
    own = api.request(WORKFORCE + "/onboarding/programs", actor="employee")["items"]
    current = next(row for row in own if row["workforce_assignment_id"] == assignment["id"])
    return {"employee_programs": len(own), "steps": [current["completed_count"], current["total_count"]], "changed": True}


def close_practice(api):
    api.login("hr")
    path = STUDENTS + "/opportunities"
    items = api.request(path, actor="hr")["items"]
    place = next(row for row in items if row["id"] == PRACTICE)
    if (place.get("is_synthetic") is not True or place.get("organization_id") != ORG
            or (place["starts_on"], place["ends_on"]) != ("2004-03-03", "2009-04-05")):
        raise ValueError("Practice provenance changed")
    if place["status"] == "closed" and place.get("close_reason") == PRACTICE_REASON:
        return {"id": PRACTICE, "status": "closed", "changed": False}
    if place["status"] != "published" or place["revision"] != 2:
        raise ValueError("Practice state or revision changed")
    if any(item["opportunity_id"] == PRACTICE for resource in ("applications", "placements")
           for item in api.request(STUDENTS + "/" + resource, actor="hr")["items"]):
        raise ValueError("Practice now has linked records; leaving it intact")
    closed = api.request(path + f"/{PRACTICE}/close", actor="hr", body={
        "expected_revision": place["revision"], "reason": PRACTICE_REASON,
    })
    return {"id": PRACTICE, "status": closed["status"], "revision": closed["revision"], "changed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", choices=("names", "workflow", "workforce", "practice"))
    parser.add_argument("--base", default="http://gateway:8080")
    parser.add_argument("--fixture", type=Path, default=Path(os.getenv("FIXTURE_DIR", "/srv/fixtures/wave-1")) / "actors.json")
    args = parser.parse_args()
    if not args.apply:
        result = {"mode": "plan only", "names": list(DEMO_NAMES),
                  "workflow": {code: [str(ident), target] for code, (ident, target) in WORKFLOW.items()},
                  "workforce_actor": EMPLOYEE_ACTOR, "practice": PRACTICE}
    elif args.apply in ("names", "workflow"):
        from sqlalchemy.exc import SQLAlchemyError

        try:
            result = (curate_names if args.apply == "names" else curate_workflow)()
        except SQLAlchemyError as exc:
            raise ValueError(f"Database operation failed: {type(exc).__name__}") from None
    else:
        api = Gateway(args.base, args.fixture)
        try:
            result = (curate_workforce if args.apply == "workforce" else close_practice)(api)
        finally:
            api.close()
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
