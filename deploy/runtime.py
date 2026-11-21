"""Run the existing service entry point. No implicit fixture/actor seed.

Migrations are explicit one-shot jobs, never raced by multiple API replicas.
The readiness probe checks storage as well as a live HTTP listener.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.request

SERVICES = {
    "legacy": ("app.main:app", False),
    "workforce": ("workforce.api:create_app", True),
    "requirements": ("requirements_service.main:app", False),
    "hiring": ("hiring.api:create_app", True),
    "students": ("students.main:app", False),
    "social-support": ("support.main:app", False),
    "mobility": ("mobility.main:app", False),
    "recognition": ("recognition.api:create_app", True),
    "feedback": ("feedback.api:create_app", True),
}


def migrate(service):
    if service in {"legacy", "requirements", "students", "mobility"}:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
    elif service == "hiring":
        subprocess.run(["python", "-m", "hiring", "migrate"], check=True)
    elif service == "workforce":
        from workforce.config import Settings
        from workforce.database import make_engine, migrate as upgrade
        engine = make_engine(Settings().database_url)
        upgrade(engine)
        engine.dispose()
    # The three direct-SQLite services initialize schemas in their app factories.


def check(service):
    with urllib.request.urlopen("http://127.0.0.1:8000/openapi.json", timeout=5) as response:
        assert json.load(response)["openapi"]
    sqlite_paths = {
        "social-support": Path(os.environ.get("SUPPORT_DATA_DIR", "/data")) / "support.sqlite3",
        "recognition": Path(os.environ.get("RECOGNITION_DB", "/data/recognition.db")),
        "feedback": Path(os.environ.get("FEEDBACK_DB", "/data/feedback.db")),
    }
    if service in sqlite_paths:
        # mode=rw must fail if startup did not create the actual database.
        connection = sqlite3.connect(f"file:{sqlite_paths[service]}?mode=rw", uri=True, timeout=3)
        try:
            assert connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] > 0
        finally:
            connection.close()
    else:
        from sqlalchemy import create_engine, text
        key = {"students": "STUDENTS_DATABASE_URL", "mobility": "MOBILITY_DATABASE_URL"}.get(service, "DATABASE_URL")
        engine = create_engine(os.environ[key])
        try:
            with engine.connect() as connection:
                assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            engine.dispose()


def main():
    service = os.environ["SERVICE_ID"]
    target, factory = SERVICES[service]
    action = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if action == "migrate":
        migrate(service)
        return
    if action == "check":
        check(service)
        return
    if action != "serve":
        raise SystemExit(f"Unknown runtime action: {action}")
    command = ["uvicorn", target, "--host", "0.0.0.0", "--port", "8000", "--workers", "1",
               "--root-path", f"/{service}", "--no-access-log", "--proxy-headers",
               "--forwarded-allow-ips", os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")]
    if factory:
        command.append("--factory")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
