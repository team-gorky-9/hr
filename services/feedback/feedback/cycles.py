import json
import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response

from feedback.dependencies import Context
from feedback.schemas import CodeIssue, CycleCreate, ResponseCreate, Revision
from feedback.store import (
    check_revision,
    check_state,
    digest,
    fail,
    get,
    new,
    require_assignment,
    save,
    rows,
    transaction,
)

router = APIRouter()
PRIVACY_NOTICE = (
    "Учебный добровольный пульс. Ответ хранится без учётки, кода и точного времени. "
    "Первичные ответы не доступны HR или руководителю через API. "
    "Внешние сетевые журналы и наблюдение оператора могут позволить связать отправку с человеком; "
    "абсолютная анонимность и защита от косвенного узнавания не гарантируются."
)


@router.post("/cycles", status_code=201)
def create_cycle(body: CycleCreate, ctx: Context):
    db, actor = ctx
    require_assignment(actor, "organizer")
    cycle = new(actor, **body.model_dump(), status="draft")
    return save(db, "cycle", cycle, actor, "create", True)


def transition(cycle_id, body, ctx, before, after):
    db, actor = ctx
    require_assignment(actor, "organizer")
    c = get(db, "cycle", cycle_id, actor)
    check_revision(c, body.expected_revision)
    check_state(c["status"] == before)
    c["status"] = after
    return save(db, "cycle", c, actor, after)


@router.post("/cycles/{cycle_id}/open")
def open_cycle(cycle_id: UUID, body: Revision, ctx: Context):
    return transition(cycle_id, body, ctx, "draft", "open")


@router.post("/cycles/{cycle_id}/close")
def close_cycle(cycle_id: UUID, body: Revision, ctx: Context):
    return transition(cycle_id, body, ctx, "open", "closed")


@router.post("/cycles/{cycle_id}/access-codes")
def issue_codes(cycle_id: UUID, body: CodeIssue, ctx: Context, response: Response):
    db, actor = ctx
    require_assignment(actor, "organizer")
    c = get(db, "cycle", cycle_id, actor)
    check_state(c["status"] == "open")
    group = next((g for g in c["groups"] if g["key"] == body.group_key), None)
    if group is None:
        fail(422, "UNKNOWN_GROUP")
    issued = db.execute(
        "SELECT count(*) FROM access_codes WHERE cycle_id=? AND group_key=?", (str(cycle_id), body.group_key)
    ).fetchone()[0]
    if issued + body.count > group["eligible_count"]:
        fail(409, "CODE_CAPACITY_EXCEEDED")
    codes = [secrets.token_urlsafe(32) for _ in range(body.count)]
    db.executemany(
        "INSERT INTO access_codes VALUES(?,?,?,0)",
        [(digest(code), str(cycle_id), body.group_key) for code in codes],
    )
    response.headers["Cache-Control"] = "no-store"
    return {"codes": codes}


@router.get("/cycles/{cycle_id}/form")
def form(cycle_id: UUID, request: Request):
    with transaction(request.app.state.database_path) as db:
        c = get(db, "cycle", cycle_id)
        if c["status"] == "draft":
            fail(404, "NOT_FOUND")
        return {
            **{
                key: c[key]
                for key in ("id", "title", "question_version", "questions", "topic_options", "status")
            },
            "privacy_notice": PRIVACY_NOTICE,
        }


@router.post("/cycles/{cycle_id}/responses", status_code=201)
def submit(cycle_id: UUID, body: ResponseCreate, request: Request):
    # Deliberately no authentication dependency; cookies/Authorization do not enter persistence.
    with transaction(request.app.state.database_path) as db:
        c = get(db, "cycle", cycle_id)
        check_state(c["status"] == "open")
        questions = {q["key"]: q for q in c["questions"]}
        if len(body.answers) != len(questions) or {a.question_key for a in body.answers} != set(questions):
            fail(422, "QUESTION_SET_MISMATCH")
        if any(
            not questions[a.question_key]["min"] <= a.value <= questions[a.question_key]["max"]
            for a in body.answers
        ):
            fail(422, "OUT_OF_RANGE")
        if body.topic_key not in {t["key"] for t in c["topic_options"]}:
            fail(422, "UNKNOWN_TOPIC")
        code_hash = digest(body.access_code)
        code = db.execute(
            "SELECT * FROM access_codes WHERE digest=? AND cycle_id=?", (code_hash, str(cycle_id))
        ).fetchone()
        if code is None:
            fail(404, "INVALID_CODE")
        if code["used"]:
            fail(409, "CODE_ALREADY_USED")
        db.execute("UPDATE access_codes SET used=1 WHERE digest=?", (code_hash,))
        db.execute(
            "INSERT INTO responses VALUES(?,?,?,?,?)",
            (
                str(uuid4()),
                str(cycle_id),
                code["group_key"],
                json.dumps([a.model_dump() for a in body.answers]),
                body.topic_key,
            ),
        )
    return {"accepted": True}


@router.get("/session")
def session(ctx: Context):
    _, actor = ctx
    return {key: actor[key] for key in ("id", "name", "roles", "assignments", "group_key")}


@router.get("/cycles")
def list_cycles(ctx: Context):
    db, actor = ctx
    organizer = "organizer" in actor["assignments"]
    return {"items": [
        ({key: cycle[key] for key in ("id", "title", "status", "revision", "question_version")}
         | ({"groups": cycle["groups"]} if organizer else {}))
        for cycle in rows(db, "cycle", actor)
        if organizer or (cycle["status"] != "draft" and "employee" in actor["roles"]
                         and actor["group_key"] in {g["key"] for g in cycle["groups"]})
    ]}
