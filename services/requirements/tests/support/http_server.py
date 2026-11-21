"""Real loopback HTTP server in an isolated process for acceptance tests."""
from contextlib import contextmanager
import os
import socket
import subprocess
import sys
import time

import httpx


@contextmanager
def running_server(settings):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL=settings.database_url,
        FILE_ROOT=str(settings.file_root),
        AUTH_MODE="fixture",
        RABBITMQ_URL=settings.rabbitmq_url,
        OUTBOX_POLL_INTERVAL_SEC="0",
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "requirements_service.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"HTTP server exited: {process.returncode}")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("HTTP server did not become healthy")
                time.sleep(0.1)
            yield client, process
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
