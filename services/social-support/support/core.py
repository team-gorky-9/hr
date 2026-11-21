"""Local durable cases. Every command checks its revision inside a write transaction."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4, uuid5, NAMESPACE_URL

ROOT = Path(__file__).resolve().parents[1]

def uid():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc).isoformat()

def fixture_id(name):
    return str(uuid5(NAMESPACE_URL, "support-training-v1/" + name))

class Problem(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message

def fail(code, message, status=409):
    raise Problem(status, code, message)

def not_found():
    fail("NOT_FOUND", "Дело или документ недоступны.", 404)

def check_revision(case, expected):
    if case["revision"] != expected:
        fail("STALE_REVISION", "Перечитайте текущую редакцию.")

def state(case, *allowed):
    if case["status"] not in allowed:
        fail("INVALID_STATE", "Действие недоступно в текущем состоянии.")

def owner(case, actor):
    return case["applicant_actor_id"] == actor["actor_id"]

def assigned(case, actor, role):
    return (not owner(case, actor) and role in actor["roles"]
            and case.get("assigned_" + role + "_id") == actor["actor_id"]
            and case["status"] != "draft")

def staff(case, actor):
    return assigned(case, actor, "specialist") or assigned(case, actor, "secretary")

def require_owner(case, actor):
    if not owner(case, actor):
        not_found()

def require_assigned(case, actor, role):
    if not assigned(case, actor, role):
        not_found()

def can_read(case, actor):
    return owner(case, actor) or staff(case, actor)

def document_view(doc):
    return {k: v for k, v in doc.items() if k != "storage_key"}

def queue_view(case):
    return {k: case[k] for k in ("id", "revision", "number", "support_type",
                                 "submitted_at", "status")} | {"applicant_ref": case["applicant_actor_id"]}

def case_view(case, actor):
    if not can_read(case, actor):
        not_found()
    if staff(case, actor):
        result = dict(case)
    else:
        keys = ("id", "organization_id", "applicant_actor_id", "rule_version_id",
                "support_type", "revision", "status", "statement", "number",
                "submitted_at", "created_at", "submissions")
        result = {k: case[k] for k in keys}
    result["documents"] = [document_view(d) for d in case["documents"]
                           if staff(case, actor) or d["visibility"] == "applicant"]
    return result

class Store:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or os.environ.get("SUPPORT_DATA_DIR", ROOT / "data")).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.files = self.data_dir / "originals"
        self.files.mkdir(exist_ok=True)
        self.db = self.data_dir / "support.sqlite3"
        fixture_path = Path(os.environ.get("SUPPORT_ACTORS_PATH", ROOT / "fixtures/actors.json"))
        self.actors = json.loads(fixture_path.read_text(encoding="utf-8-sig"))["actors"]
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, UNIQUE(case_id, revision));
                CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
            rule = {"id": fixture_id("rule"), "support_type": "training-a",
                    "title": "Учебная помощь А — не нормативный перечень",
                    "required_items": [{"key": "application", "title": "Учебное заявление"},
                                       {"key": "evidence", "title": "Учебное подтверждение"}],
                    "source_reference": "synthetic:support-training-v1",
                    "is_synthetic": True, "status": "published"}
            conn.execute("INSERT OR IGNORE INTO rules VALUES (?,?)", (rule["id"], json.dumps(rule)))

    def connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def authenticate(self, authorization):
        prefix = "Bearer fixture:"
        login = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else None
        actor = next((a for a in self.actors if a["login"] == login and a["active"]), None)
        if actor is None:
            fail("AUTH_REQUIRED", "Нужен учебный Bearer fixture:<login>.", 401)
        return actor

    def target(self, actor, actor_id, role):
        target = next((a for a in self.actors if a["actor_id"] == str(actor_id)
                       and a["organization_id"] == actor["organization_id"]
                       and a["active"] and role in a["roles"]), None)
        if target is None:
            fail("INVALID_ASSIGNEE", "Недоступный участник назначения.", 422)
        return target["actor_id"]

    @contextmanager
    def transaction(self, actor, write=False):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield Unit(conn, actor)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

class Unit:
    def __init__(self, conn, actor):
        self.conn, self.actor = conn, actor

    def rules(self):
        return [json.loads(r["payload"]) for r in self.conn.execute("SELECT payload FROM rules")]

    def rule(self, rule_id):
        rule = next((r for r in self.rules() if r["id"] == str(rule_id) and r["status"] == "published"), None)
        if rule is None:
            not_found()
        return rule

    def get(self, case_id):
        row = self.conn.execute("SELECT payload FROM cases WHERE id=? AND organization_id=?",
                                (str(case_id), self.actor["organization_id"])).fetchone()
        if row is None:
            not_found()
        return json.loads(row["payload"])

    def all(self):
        return [json.loads(row["payload"]) for row in self.conn.execute(
            "SELECT payload FROM cases WHERE organization_id=? ORDER BY rowid",
            (self.actor["organization_id"],))]

    def save(self, case, action, public=None, internal=None):
        case["revision"] += 1
        self.conn.execute("INSERT INTO cases VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                          (case["id"], case["organization_id"], json.dumps(case, ensure_ascii=False)))
        event = {"id": uid(), "case_id": case["id"], "revision": case["revision"],
                 "action": action, "actor_id": self.actor["actor_id"], "recorded_at": now(),
                 "public": public or {}, "internal": internal or {}}
        self.conn.execute("INSERT INTO history VALUES (?,?,?,?)",
                          (event["id"], case["id"], case["revision"], json.dumps(event, ensure_ascii=False)))
        return case

    def history(self, case):
        events = [json.loads(r["payload"]) for r in self.conn.execute(
            "SELECT payload FROM history WHERE case_id=? ORDER BY revision", (case["id"],))]
        if not staff(case, self.actor):
            events = [{k: v for k, v in e.items() if k != "internal"} for e in events]
        return events
