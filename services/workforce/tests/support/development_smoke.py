"""Short real HTTP demonstration; retains SQLite, OpenAPI and sanitized examples."""

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

from tests.conftest import DEPT, ORG, auth
from tests.test_development import (
    PREFIX,
    call,
    test_attempts_keep_history_and_use_latest_evidence,
    test_closure_and_selected_package_survive_new_app,
    test_goal_privacy_and_agreement,
)
from workforce.api import create_app
from workforce.config import Settings
from workforce.database import make_engine, migrate, password_hash, seed
from workforce.development.models import ResultPackage
from workforce.models import Actor


def development_spec(full):
    paths = {path: value for path, value in full["paths"].items() if path.startswith(PREFIX)}
    schemas = {}

    def collect(value):
        if isinstance(value, dict):
            ref = value.get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[1]
                if name not in schemas:
                    schemas[name] = full["components"]["schemas"][name]
                    collect(schemas[name])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(paths)
    return {
        "openapi": full["openapi"],
        "info": full["info"],
        "paths": paths,
        "components": {"schemas": schemas, "securitySchemes": full["components"]["securitySchemes"]},
    }


def main():
    directory = Path(tempfile.mkdtemp(prefix="development-smoke-"))
    settings = Settings(database_url=f"sqlite:///{directory / 'workforce.db'}", auth_mode="workforce")
    app = create_app(settings)
    migrate(app.state.engine)
    seed(app.state.engine, settings)
    with Session(app.state.engine) as session, session.begin():
        for role, suffix in (("employee", "204"), ("department", "203")):
            actor_id = "00000000-0000-4000-8000-000000000" + suffix
            session.add(
                Actor(
                    id=actor_id,
                    login=role + "_other",
                    organization_id=ORG,
                    active=True,
                    password_hash=password_hash("123"),
                    grants=[
                        {
                            "role": role,
                            "scope_type": "self" if role == "employee" else "department",
                            "scope_id": actor_id if role == "employee" else DEPT,
                        }
                    ],
                )
            )
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        address = f"http://127.0.0.1:{listener.getsockname()[1]}"
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Development HTTP server did not start")
                time.sleep(0.05)
            with httpx.Client(base_url=address, timeout=10, trust_env=False) as client:
                test_goal_privacy_and_agreement(client)
                test_attempts_keep_history_and_use_latest_evidence(client)
                test_closure_and_selected_package_survive_new_app(client, app)
                owner = auth(client, "employee")
                plans = call(client, "GET", "/plans", owner)["items"]
                closed = next(row for row in plans if row["status"] == "closed")
                histories = [
                    call(client, "GET", f"/plans/{row['id']}/submissions", owner)["items"]
                    for row in plans
                    if row["status"] == "active"
                ]
                history = next(items for items in histories if items)
                # The denied reviewer has the SAME department role and organization as the appointed one.
                other = auth(client, "department_other")
                call(
                    client,
                    "POST",
                    f"/submissions/{history[0]['id']}/review",
                    other,
                    {
                        "results": [
                            {"criterion_key": "sources", "result": "confirmed", "reason": "Чужое решение"}
                        ],
                    },
                    404,
                )
                stranger = auth(client, "employee_other")
                assert call(client, "GET", "/plans", stranger)["items"] == []
                call(client, "GET", f"/plans/{closed['id']}", stranger, status=404)
                private = call(
                    client,
                    "POST",
                    "/goals",
                    owner,
                    {"title": "Личный черновик", "description": "Ещё никому не отправлен"},
                    201,
                )
                call(client, "GET", f"/goals/{private['id']}", stranger, status=404)
                call(client, "GET", f"/goals/{private['id']}", auth(client, "hr"), status=404)
                package = call(
                    client,
                    "POST",
                    f"/plans/{closed['id']}/share-result",
                    owner,
                    {"criterion_keys": ["sources"], "purpose": "Обсудить участие в проекте"},
                )
                spec = development_spec(client.get("/openapi.json").json())
                operations = sum(len(value) for value in spec["paths"].values())
                assert operations == 17
                # Workforce overrides FastAPI's default validation-error envelope.
                error_schema = spec["paths"][PREFIX + "/goals"]["post"]["responses"]["422"]
                assert error_schema["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
                assert client.get(PREFIX + "/goals").status_code == 401
                examples = {
                    "is_synthetic": True,
                    "plan": closed,
                    "package": package,
                    "history": call(client, "GET", f"/plans/{closed['id']}/submissions", owner),
                    "progress": call(client, "GET", f"/plans/{closed['id']}/progress", owner),
                }
                for name, data in (("openapi.json", spec), ("examples.json", examples)):
                    (directory / name).write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            app.state.engine.dispose()
    engine = make_engine(settings.database_url)
    try:
        with Session(engine) as session:
            stored = session.scalar(select(ResultPackage).where(ResultPackage.id == package["package_id"]))
            assert stored is not None and len(stored.items) == 1
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "artifacts": str(directory),
                "openapi_operations": operations,
                "persisted_plan_id": closed["id"],
                "persisted_package_id": package["package_id"],
                "outsider_employee": "404 / empty list",
                "unassigned_reviewer": "404",
                "progress": "2/2",
                "package_items": 1,
                "delivery_status": "not_sent",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
