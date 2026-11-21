from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTORS = json.loads((ROOT / "fixtures/actors.json").read_text(encoding="utf-8-sig"))["actors"]

def actor_id(login):
    return next(a["actor_id"] for a in ACTORS if a["login"] == login)

class Server:
    def __init__(self, directory):
        self.directory = directory
        self.trace = []
        self.process = None

    def start(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, SUPPORT_DATA_DIR=str(self.directory), PYTHONIOENCODING="utf-8")
        self.log = (self.directory / "server.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "support.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=self.log, stderr=self.log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.client = httpx.Client(base_url=self.base, timeout=10, trust_env=False)
        for _ in range(100):
            if self.process.poll() is not None:
                raise RuntimeError((self.directory / "server.log").read_text(encoding="utf-8"))
            try:
                if self.client.get("/openapi.json").status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            time.sleep(.05)
        self.stop()
        raise RuntimeError("Local HTTP server did not start")

    def stop(self):
        self.client.close()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)
        self.log.close()

    def restart(self):
        self.stop()
        self.start()

    def call(self, method, path, login="employee", status=200, **kwargs):
        response = self.client.request(method, "/api/v1/support" + path,
                                       headers={"Authorization": "Bearer fixture:" + login}, **kwargs)
        assert response.status_code == status, (method, path, response.status_code, response.text)
        if response.headers.get("content-type", "").startswith("application/json"):
            result = response.json()
            self.trace.append({"actor": login, "method": method, "path": path,
                               "status": status, "response": result})
            return result
        return response

    def export(self, name):
        target = os.environ.get("SUPPORT_REPORT_DIR")
        if target:
            dest = Path(target)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{name}-openapi.json").write_text(
                json.dumps(self.client.get("/openapi.json").json(), ensure_ascii=False, indent=2), encoding="utf-8")
            (dest / f"{name}-examples.json").write_text(
                json.dumps({"is_synthetic": True, "source": "support-training-v1", "trace": self.trace},
                           ensure_ascii=False, indent=2), encoding="utf-8")

@pytest.fixture
def server(tmp_path):
    api = Server(tmp_path)
    try:
        api.start()
        yield api
    finally:
        if api.process:
            api.stop()

def get_case(api, ident, login="employee"):
    return api.call("GET", f"/cases/{ident}", login)

def upload(api, case, item="application", content=b"synthetic attachment", login="employee", **kwargs):
    return api.call("POST", f'/cases/{case["id"]}/documents', login, status=201,
                    data={"expected_revision": case["revision"], "item_key": item, **kwargs},
                    files={"file": ("../../original.txt", content, "text/plain")})

def submitted(api, login="employee"):
    rule = api.call("GET", "/rules", login)[0]
    case = api.call("POST", "/cases", login, status=201,
                    json={"rule_version_id": rule["id"], "statement": "Учебное заявление: без реальных личных данных"})
    upload(api, case, login=login)
    case = get_case(api, case["id"], login)
    upload(api, case, "evidence", login=login)
    case = get_case(api, case["id"], login)
    return api.call("POST", f'/cases/{case["id"]}/submit', login,
                    json={"expected_revision": case["revision"]})

def assign(api, case, secretary="secretary"):
    api.call("POST", f'/cases/{case["id"]}/assign', "coordinator", json={
        "expected_revision": case["revision"], "specialist_actor_id": actor_id("specialist"),
        "secretary_actor_id": actor_id(secretary), "assignment_basis": "synthetic: assignment v1"})
    return get_case(api, case["id"], "specialist")
