"""Real HTTP + AMQP smoke, split into phases so the broker/API can be stopped externally."""

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from tests.support.broker import publish
from workforce.config import Settings
from workforce.worker import connect, topology


def http(base, path, token=None, body=None, key=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["Idempotency-Key"] = key
    request = Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def eventually(operation, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        result = operation()
        if predicate(result):
            return result
        if time.monotonic() >= deadline:
            raise AssertionError("Expected condition was not reached before timeout")
        time.sleep(0.25)


def prepare(base, settings):
    assert http(base, "/ready")[1] == {"status": "ok", "broker": "available"}
    status, login = http(base, "/api/v1/sessions", body={"login": "hr", "password": "123"}, key=str(uuid4()))
    assert status == 201
    token = login["access_token"]
    event = json.loads((settings.fixture_dir / "events.json").read_text(encoding="utf-8"))["events"][0]
    event.update(event_id=str(uuid4()), aggregate_id=str(uuid4()), correlation_id=str(uuid4()))
    event["payload"]["case_id"] = event["aggregate_id"]
    event["payload"]["person_ref"]["id"] = str(uuid4())
    event["payload"]["basis"]["reference"] = "SMOKE-" + event["aggregate_id"]
    connection = connect(settings)
    try:
        channel = connection.channel()
        topology(channel)
        queue = "w1.hiring.assignment.registered"
        channel.queue_declare(queue=queue, durable=True)
        channel.queue_bind(queue=queue, exchange="w1.workforce", routing_key="assignment.registered")
        publish(channel, event, repeat=2)
    finally:
        connection.close()

    def find_intake():
        _, page = http(base, "/api/v1/intakes?limit=100", token)
        return next((item for item in page["items"] if item["source_case_id"] == event["aggregate_id"]), None)

    item = eventually(find_intake, lambda value: value is not None)
    return {"token": token, "event": event, "intake": item, "key": str(uuid4())}


def register(base, state, expect_offline):
    if expect_offline:
        assert http(base, "/ready")[1] == {"status": "ok", "broker": "unavailable"}
    before_ids = {
        row["event_id"] for row in http(base, "/api/v1/deliveries?limit=100", state["token"])[1]["items"]
    }
    body = {
        "expected_revision": state["intake"]["revision"],
        "employee_id": None,
        "create_employee": {"display_name": "Марина Учебная"},
        "identity_basis": "Synthetic smoke check",
    }
    status, result = http(
        base, f"/api/v1/intakes/{state['intake']['id']}/register", state["token"], body, state["key"]
    )
    assert status == 200, {"status": status, "response": result}
    state.update(result=result, body=body)
    new_deliveries = [
        row
        for row in http(base, "/api/v1/deliveries?limit=100", state["token"])[1]["items"]
        if row["event_id"] not in before_ids
    ]
    assert len(new_deliveries) == 1
    state["delivery_event_id"] = new_deliveries[0]["event_id"]
    if expect_offline:
        delivery = eventually(
            lambda: http(base, "/api/v1/deliveries?limit=100", state["token"])[1],
            lambda page: any(
                row["event_id"] == state["delivery_event_id"]
                and row["status"] in {"pending", "failed"}
                and row["attempts"] > 0
                for row in page["items"]
            ),
        )
        assert delivery["items"]
    return state


def recover(base, settings, state):
    assert http(base, "/ready")[1] == {"status": "ok", "broker": "available"}
    connection = connect(settings)
    try:
        channel = connection.channel()

        def read():
            method, _, body = channel.basic_get("w1.hiring.assignment.registered", auto_ack=False)
            if method is None:
                return None
            result = json.loads(body)
            channel.basic_ack(method.delivery_tag)
            return result if result["correlation_id"] == state["event"]["correlation_id"] else None

        result = eventually(read, lambda value: value is not None, timeout=60)
        assert result["payload"]["assignment_id"] == state["result"]["assignment"]["id"]
        assert result["event_id"] == state["delivery_event_id"]
        assert result["payload"]["source_event_id"] == state["event"]["event_id"]
        assert result["payload"]["source_case_revision"] == state["event"]["aggregate_revision"]
        return result
    finally:
        connection.close()


def restart(base, state):
    assert http(base, "/api/v1/session", state["token"])[0] == 200
    status, employee = http(base, f"/api/v1/employees/{state['result']['employee']['id']}", state["token"])
    assert status == 200
    assert len(employee["assignments"]) == 1
    status, result = http(
        base, f"/api/v1/intakes/{state['intake']['id']}/register", state["token"], state["body"], state["key"]
    )
    assert status == 200 and result == state["result"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["normal", "prepare", "offline", "recover", "restart"])
    parser.add_argument("--url", default="http://127.0.0.1:8101")
    parser.add_argument("--state", type=Path, default=Path("workforce-smoke-state.json"))
    args = parser.parse_args()
    settings = Settings()
    if args.phase in {"normal", "prepare"}:
        state = prepare(args.url, settings)
    else:
        state = json.loads(args.state.read_text(encoding="utf-8"))
    if args.phase in {"normal", "offline"}:
        state = register(args.url, state, args.phase == "offline")
    if args.phase in {"normal", "recover"}:
        recover(args.url, settings, state)
    if args.phase == "restart":
        restart(args.url, state)
    args.state.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": args.phase,
                "passed": True,
                "intake_id": state["intake"]["id"],
                "employee_id": state.get("result", {}).get("employee", {}).get("id"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
