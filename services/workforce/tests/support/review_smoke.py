"""Apply/keep a corrected readiness version through real HTTP and RabbitMQ."""

import argparse
import copy
import json
from pathlib import Path
from uuid import uuid4

from tests.support.broker import publish
from tests.support.smoke import eventually, http
from workforce.config import Settings
from workforce.worker import connect, topology


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("decision", choices=["apply", "keep"])
    parser.add_argument("--url", default="http://127.0.0.1:8101")
    parser.add_argument("--state", type=Path, default=Path("workforce-smoke-state.json"))
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    settings = Settings()
    event = copy.deepcopy(state["event"])
    source_revision = state.get("review_source_revision", event["aggregate_revision"]) + 1
    event.update(event_id=str(uuid4()), correlation_id=str(uuid4()), aggregate_revision=source_revision)
    event["payload"]["starts_on"] = "2026-11-24" if args.decision == "apply" else "2026-11-25"
    event["payload"]["basis"]["reference"] = f"SMOKE-CORRECTION-{source_revision}"
    token = state["token"]
    assignment_id = state["result"]["assignment"]["id"]
    _, employee = http(args.url, f"/api/v1/employees/{state['result']['employee']['id']}", token)
    old_assignment = next(row for row in employee["assignments"] if row["id"] == assignment_id)
    connection = connect(settings)
    try:
        channel = connection.channel()
        topology(channel)
        queue = "w1.hiring.assignment.reviewed"
        channel.queue_declare(queue=queue, durable=True)
        channel.queue_bind(queue=queue, exchange="w1.workforce", routing_key="assignment.reviewed")
        publish(channel, event, repeat=2)
        item = eventually(
            lambda: http(args.url, f"/api/v1/intakes/{state['intake']['id']}", token)[1],
            lambda row: row["status"] == "needs_review" and row["source_case_revision"] == source_revision,
        )
        body = {
            "expected_revision": item["revision"],
            "expected_assignment_revision": old_assignment["revision"],
            "decision": args.decision,
            "reason": "Synthetic review: original order remains valid" if args.decision == "keep" else None,
        }
        key = str(uuid4())
        path = f"/api/v1/intakes/{item['id']}/review"
        status, result = http(args.url, path, token, body, key)
        assert status == 200, result
        assert http(args.url, path, token, body, key)[1] == result
        assert result["assignment"]["id"] == assignment_id
        assert result["intake"]["status"] == "registered"
        expected_date = (
            event["payload"]["starts_on"] if args.decision == "apply" else old_assignment["starts_on"]
        )
        assert result["assignment"]["starts_on"] == expected_date

        def read():
            method, _, raw = channel.basic_get(queue, auto_ack=False)
            if method is None:
                return None
            message = json.loads(raw)
            channel.basic_ack(method.delivery_tag)
            return message if message["correlation_id"] == event["correlation_id"] else None

        message = eventually(read, lambda value: value is not None)
        assert message["payload"]["decision"] == args.decision
        assert message["payload"]["assignment_id"] == assignment_id
        assert message["payload"]["starts_on"] == expected_date
        assert message["payload"]["source_event_id"] == event["event_id"]
        state["review_source_revision"] = source_revision
        args.state.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "decision": args.decision,
                    "passed": True,
                    "assignment_id": assignment_id,
                    "starts_on": expected_date,
                    "source_case_revision": source_revision,
                }
            )
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
