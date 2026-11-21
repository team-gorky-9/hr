from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from alembic import command
from alembic.config import Config
import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/api/v1/mobility"
ORG = "00000000-0000-4000-8000-000000000001"
EMPLOYEE = "00000000-0000-4000-8000-000000000101"
OWNER = "00000000-0000-4000-8000-000000000102"
MANAGER = "00000000-0000-4000-8000-000000000103"
MANAGER2 = "00000000-0000-4000-8000-000000000104"
SOURCE = "fixture:mobility-training-v1:employee-manager"


def headers(login):
    return {"Authorization": f"Bearer fixture:{login}"}


@contextmanager
def server(database_url, actors_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(MOBILITY_DATABASE_URL=database_url, MOBILITY_ACTORS_PATH=str(actors_path))
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "mobility.main:app",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"], cwd=ROOT, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited {process.returncode}")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Server startup timed out")
            yield client
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def database_url(tmp_path):
    url = f"sqlite:///{tmp_path / 'mobility.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    return url


@pytest.fixture
def actors_path(tmp_path):
    path = tmp_path / "actors.json"
    shutil.copyfile(ROOT / "fixtures/actors.json", path)
    return path


@pytest.fixture
def client(database_url, actors_path):
    with server(database_url, actors_path) as api:
        yield api


def post(client, path, body, login="owner", expected=200):
    response = client.post(PREFIX + path, headers=headers(login), json=body)
    assert response.status_code == expected, response.text
    return response.json()


def get(client, path, login="employee", expected=200):
    response = client.get(PREFIX + path, headers=headers(login))
    assert response.status_code == expected, response.text
    return response.json()


def opportunity(client, title="Организация учебной практики"):
    row = post(client, "/opportunities", dict(organization_id=ORG, owner_actor_id=OWNER,
        title=title, result_description="Подготовить программу практики и расписание",
        starts_on="2026-12-01", ends_on="2026-12-31", time_percent=20), expected=201)
    return post(client, f"/opportunities/{row['id']}/open", {"expected_revision": 1})


def selected(client):
    opp = opportunity(client)
    interest = post(client, f"/opportunities/{opp['id']}/interests", {"comment": "Учебный личный интерес"},
                    "employee", 201)
    return post(client, f"/interests/{interest['id']}/select", {"expected_revision": 1})


def evidence(client, part, examples):
    destination = os.environ.get("MOBILITY_REPORT_DIR")
    if destination:
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        for suffix, payload in [("examples", {"source": "mobility-training-v1, synthetic", **examples}),
                                ("openapi", client.get("/openapi.json").json())]:
            (directory / f"wave-4{part}-mobility-{suffix}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
