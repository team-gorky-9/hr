"""Check role/123 login, native cross-service sessions, revocation and persistence."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["create", "verify"])
parser.add_argument("--base", default="http://127.0.0.1:8080")
parser.add_argument("--state", type=Path, required=True)
args = parser.parse_args()


def call(path, method="GET", body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(args.base.rstrip("/") + path,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, exc.read()
    assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    return json.loads(payload) if payload else None


if args.action == "create":
    call("/workforce/api/v1/sessions", "POST", {"login": "hr", "password": "wrong"}, expected=401)
    result = call("/workforce/api/v1/sessions", "POST", {"login": "hr", "password": "123"}, expected=201)
    token = result["access_token"]
    assert call("/workforce/api/v1/session", token=token)["login"] == "hr"
    call("/hiring/api/v1/cases", token=token)
    call("/requirements/api/v1/positions", token=token)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
        json.dump({"token": token}, stream)
    print("Role login and shared Workforce/Hiring/Requirements session OK; persistence probe saved privately.")
else:
    token = json.loads(args.state.read_text())["token"]
    assert call("/workforce/api/v1/session", token=token)["login"] == "hr"
    call("/hiring/api/v1/cases", token=token)
    call("/requirements/api/v1/positions", token=token)
    call("/workforce/api/v1/session", "DELETE", token=token, expected=204)
    call("/workforce/api/v1/session", token=token, expected=401)
    call("/hiring/api/v1/cases", token=token, expected=401)
    call("/requirements/api/v1/positions", token=token, expected=401)
    args.state.unlink()
    print("Session survived container recreation; logout revoked it in all three services.")
