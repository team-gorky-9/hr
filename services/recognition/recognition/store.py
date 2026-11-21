"""Durable local store. Every command, including capacity checks, owns one transaction."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException

DEMO_IDS = {
    name: str(uuid5(NAMESPACE_URL, "recognition-demo/" + name))
    for name in (
        "alice",
        "bob",
        "reader",
        "organizer",
        "moderator",
        "moderator2",
        "reviewer",
        "manager",
        "facilitator",
        "outsider",
    )
}
DEMO_ORG = str(uuid5(NAMESPACE_URL, "recognition-demo/organization"))


def fail(status, code):
    raise HTTPException(status, detail={"code": code})


def now():
    return datetime.now(UTC).isoformat()


def connect(path):
    connection = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with transaction(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS actors ("
            "id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, name TEXT NOT NULL, "
            "token_hash TEXT UNIQUE NOT NULL, roles TEXT NOT NULL, assignments TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            "id TEXT PRIMARY KEY, kind TEXT NOT NULL, organization_id TEXT NOT NULL, "
            "parent_id TEXT REFERENCES records(id), actor_id TEXT REFERENCES actors(id), "
            "status TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0), "
            "data TEXT NOT NULL CHECK(json_valid(data)))"
        )
        db.execute("CREATE INDEX IF NOT EXISTS record_kind_org ON records(kind, organization_id, id)")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_active_registration "
            "ON records(parent_id, actor_id) WHERE kind='registration' AND status != 'cancelled'"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS history ("
            "record_id TEXT NOT NULL REFERENCES records(id), revision INTEGER NOT NULL, "
            "actor_id TEXT NOT NULL REFERENCES actors(id), action TEXT NOT NULL, "
            "occurred_at TEXT NOT NULL, snapshot TEXT NOT NULL, PRIMARY KEY(record_id, revision))"
        )


@contextmanager
def transaction(path):
    db = connect(path)
    try:
        # A database lock (not a Python lock) covers reads and the resulting writes.
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def seed_demo(path):
    initialize(path)
    with transaction(path) as db:
        for name, actor_id in DEMO_IDS.items():
            roles = ["employee"]
            assignments = []
            if name in ("organizer", "moderator", "moderator2"):
                roles.append("hr")
            if name == "organizer":
                assignments = ["organizer", "publisher"]
            if name.startswith("moderator"):
                assignments = ["moderator"]
            if name in ("reviewer", "manager"):
                roles.append("department")
            org = str(uuid5(NAMESPACE_URL, "recognition-demo/other")) if name == "outsider" else DEMO_ORG
            db.execute(
                "INSERT OR IGNORE INTO actors VALUES(?,?,?,?,?,?)",
                (
                    actor_id,
                    org,
                    name,
                    hashlib.sha256(("demo-" + name).encode()).hexdigest(),
                    json.dumps(roles),
                    json.dumps(assignments),
                ),
            )


def authenticate(db, token):
    row = db.execute(
        "SELECT * FROM actors WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)
    ).fetchone()
    if row is None:
        fail(401, "UNAUTHENTICATED")
    actor = dict(row)
    actor.pop("token_hash")
    for key in ("roles", "assignments"):
        actor[key] = json.loads(actor[key])
    return actor


def peer(db, actor, actor_id, role=None):
    row = db.execute(
        "SELECT * FROM actors WHERE id=? AND organization_id=?", (str(actor_id), actor["organization_id"])
    ).fetchone()
    if row is None or (role and role not in json.loads(row["roles"])):
        fail(422, "INVALID_ACTOR")
    return dict(row)


def require_assignment(actor, assignment):
    if assignment not in actor["assignments"]:
        fail(404, "NOT_FOUND")


def require_employee(actor):
    if "employee" not in actor["roles"]:
        fail(404, "NOT_FOUND")


def get(db, kind, record_id, actor):
    row = db.execute(
        "SELECT data FROM records WHERE id=? AND kind=? AND organization_id=?",
        (str(record_id), kind, actor["organization_id"]),
    ).fetchone()
    if row is None:
        fail(404, "NOT_FOUND")
    return json.loads(row["data"])


def rows(db, kind, actor):
    return [
        json.loads(row["data"])
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
        created_at=now(),
        updated_at=now(),
        created_by=actor["id"],
        **fields,
    )


def save(db, kind, record, actor, action, creating=False):
    record["updated_at"] = now()
    if not creating:
        record["revision"] += 1
    payload = json.dumps(record, ensure_ascii=False)
    parent = record.get("event_id", record.get("campaign_id"))
    values = (
        record["id"],
        kind,
        record["organization_id"],
        parent,
        record.get("actor_id"),
        record["status"],
        record["revision"],
        payload,
    )
    if creating:
        db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?,?)", values)
    else:
        db.execute(
            "UPDATE records SET status=?,revision=?,data=? WHERE id=?",
            (record["status"], record["revision"], payload, record["id"]),
        )
    db.execute(
        "INSERT INTO history VALUES(?,?,?,?,?,?)",
        (record["id"], record["revision"], actor["id"], action, now(), payload),
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
            "occurred_at": row["occurred_at"],
            "snapshot": json.loads(row["snapshot"]),
        }
        for row in db.execute("SELECT * FROM history WHERE record_id=? ORDER BY revision", (record["id"],))
    ]


def page(items, limit, cursor):
    filtered = [item for item in items if cursor is None or item["id"] > str(cursor)]
    return {
        "items": filtered[:limit],
        "next_cursor": filtered[limit - 1]["id"] if len(filtered) > limit else None,
    }
