from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from alembic import command
from alembic.config import Config
import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/api/v1/students"
MENTOR = "00000000-0000-4000-8000-000000000103"
MENTOR2 = "00000000-0000-4000-8000-000000000104"


def headers(login="hr"):
    return {"Authorization": f"Bearer fixture:{login}"}


@contextmanager
def server(database_url):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(STUDENTS_DATABASE_URL=database_url, STUDENTS_MENTOR_CAPACITY="1",
               STUDENTS_ACTORS_PATH=str(ROOT / "fixtures/actors.json"))
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "students.main:app",
                                "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
                               cwd=ROOT, env=env,
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
    url = f"sqlite:///{tmp_path / 'students.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    return url


@pytest.fixture
def client(database_url):
    with server(database_url) as client:
        yield client


def post(client, path, body, login="hr", expected=200):
    response = client.post(PREFIX + path, headers=headers(login), json=body)
    assert response.status_code == expected, response.text
    return response.json()


def opportunity(client, capacity=1, mentor=MENTOR):
    row = post(client, "/opportunities", dict(title="Учебная практика", description="Разбор обращений",
               starts_on="2026-12-01", ends_on="2026-12-31", capacity=capacity,
               mentor_actor_id=mentor), expected=201)
    return post(client, f"/opportunities/{row['id']}/publish", {"expected_revision": 1})


def apply(client, opportunity_id, login="candidate"):
    return post(client, "/applications", dict(opportunity_id=opportunity_id,
                university_label="Учебный вуз", programme_label="Учебная программа", comment="Пример"),
                login, expected=201)


def placement(client):
    opp = opportunity(client)
    application = apply(client, opp["id"])
    return post(client, f"/applications/{application['id']}/assign",
                {"expected_revision": 1, "confirmation_basis": "Учебные условия сверены"})
