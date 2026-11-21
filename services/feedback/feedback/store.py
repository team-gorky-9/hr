"""Local durable store. Pulse answers never pass through management records/history."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException

DEMO_IDS = {
    name: str(uuid5(NAMESPACE_URL, "feedback-demo/" + name))
    for name in ("alice", "bob", "manager", "small-manager", "organizer", "recipient", "hr", "outsider")
}
DEMO_ORG = str(uuid5(NAMESPACE_URL, "feedback-demo/organization"))


def fail(status, code):
    raise HTTPException(status, detail={"code": code})


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def transaction(path):
    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with transaction(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS actors (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
            "name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, roles TEXT NOT NULL, "
            "assignments TEXT NOT NULL, group_key TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
            "organization_id TEXT NOT NULL, data TEXT NOT NULL CHECK(json_valid(data)))"
        )
        db.execute("CREATE INDEX IF NOT EXISTS records_kind_org ON records(kind, organization_id)")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS publication_cycle "
            "ON records(json_extract(data,'$.cycle_id')) WHERE kind='publication'"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS history (record_id TEXT REFERENCES records(id), "
            "revision INTEGER NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL, "
            "snapshot TEXT NOT NULL, PRIMARY KEY(record_id,revision))"
        )
        # Deliberately no inheritance from records: no actor, timestamp or invitation link.
        db.execute(
            "CREATE TABLE IF NOT EXISTS responses (id TEXT PRIMARY KEY, "
            "cycle_id TEXT NOT NULL REFERENCES records(id), group_key TEXT NOT NULL, "
            "answers TEXT NOT NULL CHECK(json_valid(answers)), topic_key TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS access_codes (digest TEXT PRIMARY KEY, "
            "cycle_id TEXT NOT NULL REFERENCES records(id), group_key TEXT NOT NULL, "
            "used INTEGER NOT NULL DEFAULT 0 CHECK(used IN (0,1)))"
        )


def seed_demo(path):
    initialize(path)
    with transaction(path) as db:
        for name, actor_id in DEMO_IDS.items():
            roles = ["employee"] + (["department"] if "manager" in name else [])
            if name in ("organizer", "hr", "recipient"):
                roles.append("hr")
            assignments = ["organizer", "publisher"] if name == "organizer" else []
            if name == "recipient":
                assignments = ["confidential_recipient"]
            org = str(uuid5(NAMESPACE_URL, "feedback-demo/other")) if name == "outsider" else DEMO_ORG
            db.execute(
                "INSERT OR IGNORE INTO actors VALUES(?,?,?,?,?,?,?)",
                (
                    actor_id,
                    org,
                    name,
                    digest("demo-" + name),
                    json.dumps(roles),
                    json.dumps(assignments),
                    "small" if name == "small-manager" else "large",
                ),
            )


def authenticate(db, token):
    row = db.execute("SELECT * FROM actors WHERE token_hash=?", (digest(token),)).fetchone()
    if row is None:
        fail(401, "UNAUTHENTICATED")
    result = dict(row)
    result.pop("token_hash")
    for field in ("roles", "assignments"):
        result[field] = json.loads(result[field])
    return result


def require_assignment(actor, assignment):
    if assignment not in actor["assignments"]:
        fail(404, "NOT_FOUND")


def get(db, kind, record_id, actor=None):
    row = db.execute("SELECT * FROM records WHERE id=? AND kind=?", (str(record_id), kind)).fetchone()
    if row is None or (actor and row["organization_id"] != actor["organization_id"]):
        fail(404, "NOT_FOUND")
    return json.loads(row["data"])


def rows(db, kind, actor):
    return [
        json.loads(row[0])
        for row in db.execute(
            "SELECT data FROM records WHERE kind=? AND organization_id=? ORDER BY id",
            (kind, actor["organization_id"]),
        )
    ]


def new(actor, **fields):
    return dict(
        id=str(uuid4()),
        organization_id=actor["organization_id"],
        revision=1,
        created_by=actor["id"],
        **fields,
    )


def save(db, kind, record, actor, action, creating=False):
    if not creating:
        record["revision"] += 1
    data = json.dumps(record, ensure_ascii=False)
    if creating:
        db.execute(
            "INSERT INTO records VALUES(?,?,?,?)", (record["id"], kind, record["organization_id"], data)
        )
    else:
        db.execute("UPDATE records SET data=? WHERE id=?", (data, record["id"]))
    db.execute(
        "INSERT INTO history VALUES(?,?,?,?,?)", (record["id"], record["revision"], actor["id"], action, data)
    )
    return record


def check_revision(record, expected):
    if record["revision"] != expected:
        fail(409, "STALE_REVISION")


def check_state(condition):
    if not condition:
        fail(409, "INVALID_STATE")


def history(db, record):
    return [
        {
            "revision": row["revision"],
            "actor_id": row["actor_id"],
            "action": row["action"],
            "snapshot": json.loads(row["snapshot"]),
        }
        for row in db.execute("SELECT * FROM history WHERE record_id=? ORDER BY revision", (record["id"],))
    ]
