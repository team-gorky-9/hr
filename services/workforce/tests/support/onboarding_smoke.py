"""One real loopback HTTP demo on a retained, isolated SQLite database.

Run from services/workforce: uv run python -m tests.support.onboarding_smoke
No broker, Docker or shared server is needed or modified.
"""

import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import ORG, auth
from tests.test_onboarding import PREFIX, test_intro_progress_is_persisted_and_private
from workforce.api import create_app
from workforce.config import Settings
from workforce.database import make_engine, migrate, password_hash, seed
from workforce.models import Actor
from workforce.onboarding.models import Program


def main():
    directory = Path(tempfile.mkdtemp(prefix="onboarding-smoke-"))
    settings = Settings(database_url=f"sqlite:///{directory / 'workforce.db'}", auth_mode="workforce")
    app = create_app(settings)
    migrate(app.state.engine)
    seed(app.state.engine, settings)
    seed(app.state.engine, settings)
    # A second synthetic employee account in the SAME organization, not an HR role.
    second_id = "00000000-0000-4000-8000-000000000204"
    with Session(app.state.engine) as session, session.begin():
        session.add(
            Actor(
                id=second_id,
                login="employee_other",
                organization_id=ORG,
                grants=[{"role": "employee", "scope_type": "self", "scope_id": second_id}],
                password_hash=password_hash("123"),
                active=True,
            )
        )
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Demo HTTP server did not start")
                time.sleep(0.05)
            with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
                test_intro_progress_is_persisted_and_private(client)
                hr, other = auth(client), auth(client, "employee_other")
                programs = client.get(PREFIX + "/programs", headers=hr).json()["items"]
                completed = next(row for row in programs if row["status"] == "intro_completed")
                assert client.get(PREFIX + "/programs", headers=other).json()["items"] == []
                assert client.get(PREFIX + "/programs/" + completed["id"], headers=other).status_code == 404
                spec = client.get("/openapi.json").json()
                operations = sum(len(item) for path, item in spec["paths"].items() if path.startswith(PREFIX))
                assert operations == 6
                (directory / "openapi.json").write_text(
                    json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            "base_url": base_url,
                            "openapi_operations": operations,
                            "second_employee": "404, empty list",
                            "artifacts": str(directory),
                        }
                    )
                )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            app.state.engine.dispose()
    # A fresh DB connection after HTTP shutdown proves the result was committed to disk.
    engine = make_engine(settings.database_url)
    try:
        with Session(engine) as session:
            row = session.scalar(select(Program).where(Program.status == "intro_completed"))
            assert row is not None and row.revision == 4
            assert sum(step["acknowledged_at"] is not None for step in row.steps) == 3
            print(json.dumps({"persisted_program_id": row.id, "status": row.status, "progress": "3/3"}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
