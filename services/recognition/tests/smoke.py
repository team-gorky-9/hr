"""One real loopback HTTP run; writes sanitized evidence, never bearer tokens."""

import argparse
import json
import socket
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn

from recognition.api import create_app
from recognition.store import seed_demo
from tests.test_events import event_path
from tests.test_nominations import nomination_path
from tests.test_thanks import call, thanks_path


@contextmanager
def serve(app):
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        address = f"http://127.0.0.1:{listener.getsockname()[1]}"
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("HTTP startup failed")
                time.sleep(0.02)
            with httpx.Client(base_url=address, trust_env=False, timeout=10) as client:
                yield client
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("HTTP shutdown failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["4a", "4b", "4c"], default="4a")
    args = parser.parse_args()
    directory = Path(tempfile.mkdtemp(prefix="recognition-smoke-"))
    db = directory / "recognition.db"
    seed_demo(db)
    app = create_app(db)
    with serve(app) as client:
        result = {"4a": thanks_path, "4b": nomination_path, "4c": event_path}[args.part](client)
        spec = client.get("/openapi.json").json()
    with serve(create_app(db)) as client:
        if args.part == "4a":
            saved = call(client, "GET", "/thanks/" + result["thanks_id"])
            assert saved["status"] == "withdrawn"
        elif args.part == "4b":
            saved = call(client, "GET", "/nominations/" + result["nomination_id"], "bob")
            assert saved["status"] == "selected" and saved["publication_choice"] == "allowed"
        else:
            saved = call(client, "GET", "/registrations/" + result["registration_id"], "bob")
            assert saved["status"] == "confirmed"
            assert call(client, "GET", "/events/" + result["event_id"])["available_places"] == 1
        result["reopened_revision"] = saved["revision"]
    reports = Path(__file__).resolve().parents[3] / "docs" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"wave-{args.part}-openapi.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (reports / f"wave-{args.part}-examples.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"part": args.part, "result": result, "database": str(db)}, indent=2))


if __name__ == "__main__":
    main()
