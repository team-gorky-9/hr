"""One short loopback HTTP path, restart and sanitized evidence for the frontend."""

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

from feedback.api import create_app
from feedback.store import seed_demo
from tests.test_cycle import call, cycle_path
from tests.test_publication import publication_path


@contextmanager
def serve(app):
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
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
    parser.add_argument("--part", choices=["5a", "5b"], default="5a")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="feedback-smoke-") as directory:
        db = Path(directory) / "feedback.db"
        seed_demo(db)
        with serve(create_app(db)) as client:
            result = {"5a": cycle_path, "5b": publication_path}[args.part](client, db)
            spec = client.get("/openapi.json").json()
        with serve(create_app(db)) as client:
            if args.part == "5a":
                saved = call(client, "GET", f"/cycles/{result['cycle_id']}/form", None)
                assert saved["status"] == "closed"
            else:
                saved = call(client, "GET", f"/publications/{result['publication_id']}")
                assert saved == result["publication"]
            result["reopened_status"] = saved["status"]
    reports = Path(__file__).resolve().parents[3] / "docs" / "reports"
    (reports / f"wave-{args.part}-feedback-openapi.json").write_text(
        json.dumps(spec, indent=2), encoding="utf-8"
    )
    (reports / f"wave-{args.part}-feedback-examples.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps({"part": args.part, "result": result}, indent=2))


if __name__ == "__main__":
    main()
