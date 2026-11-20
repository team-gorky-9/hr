import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.conftest import FIXTURES, auth, command
from tests.support.broker import publish
from tests.test_events import intake, register
from workforce.models import Assignment, Inbox, Intake, Outbox, now
from workforce.worker import DEAD_QUEUE, QUEUE, connect, consume_once, publish_pending, topology

pytestmark = pytest.mark.integration


@pytest.fixture
def broker(app):
    url = os.getenv("WORKFORCE_TEST_RABBITMQ_URL")
    if not url:
        pytest.skip("WORKFORCE_TEST_RABBITMQ_URL is not configured")
    if not unquote(urlparse(url).path).endswith("_test"):
        pytest.fail("Broker integration requires a dedicated *_test vhost")
    settings = replace(app.state.settings, rabbitmq_url=url)
    connection = connect(settings)
    channel = connection.channel()
    topology(channel)
    channel.queue_purge(QUEUE)
    channel.queue_purge(DEAD_QUEUE)
    queue = channel.queue_declare(queue="", exclusive=True).method.queue
    channel.queue_bind(queue=queue, exchange="w1.workforce", routing_key="assignment.registered")
    yield settings, channel, queue
    connection.close()


def example():
    event = json.loads((FIXTURES / "events.json").read_text(encoding="utf-8"))["events"][0]
    event["event_id"] = str(uuid4())
    return event


def test_real_broker_repeated_input_registration_and_output(app, client, broker):
    settings, channel, queue = broker
    event = example()
    publish(channel, event, repeat=2)
    assert consume_once(app.state.engine, settings) == 2
    headers = auth(client)
    result = register(client, intake(client, headers), headers)
    assert result.status_code == 200, result.text
    assert publish_pending(app.state.engine, settings) == 1
    method, properties, body = channel.basic_get(queue, auto_ack=False)
    assert method is not None
    received = json.loads(body)
    assert properties.delivery_mode == 2
    assert received["payload"]["assignment_id"] == result.json()["assignment"]["id"]
    assert received["payload"]["source_event_id"] == event["event_id"]
    assert received["correlation_id"] == event["correlation_id"]
    channel.basic_ack(method.delivery_tag)
    assert publish_pending(app.state.engine, settings) == 0
    assert channel.basic_get(queue, auto_ack=True)[0] is None


def test_crash_after_commit_before_ack_redelivers_without_duplicate(app, client, broker):
    settings, channel, _ = broker
    event = example()
    publish(channel, event)
    env = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "RABBITMQ_URL": settings.rabbitmq_url,
        "FIXTURE_DIR": str(settings.fixture_dir),
    }
    process = subprocess.run(
        [sys.executable, "-m", "tests.support.crash_consumer"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        timeout=30,
        capture_output=True,
        check=False,
    )
    assert process.returncode == 17, process.stderr.decode(errors="replace")
    deadline = time.monotonic() + 10
    count = 0
    while time.monotonic() < deadline and not count:
        count += consume_once(app.state.engine, settings)
        if not count:
            time.sleep(0.1)
    assert count == 1
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Intake)) == 1
        assert session.scalar(select(func.count()).select_from(Inbox)) == 1
    headers = auth(client)
    assert register(client, intake(client, headers), headers).status_code == 200
    publish(channel, event)
    consume_once(app.state.engine, settings)
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Assignment)) == 1


def test_invalid_message_is_dead_lettered_with_reason(app, client, broker):
    settings, channel, _ = broker
    event = example()
    event["organization_id"] = "00000000-0000-4000-8000-000000000002"
    publish(channel, event)
    assert consume_once(app.state.engine, settings) == 1
    method, properties, body = channel.basic_get(DEAD_QUEUE, auto_ack=False)
    assert method is not None
    assert properties.headers["reason"] == "INVALID_ORGANIZATION_OR_REFERENCE"
    assert json.loads(body)["event_id"] == event["event_id"]
    channel.basic_ack(method.delivery_tag)
    assert client.get("/api/v1/intakes", headers=auth(client)).json()["items"] == []


def test_failed_connection_then_real_delivery_recovers(app, client, broker):
    settings, channel, queue = broker
    event = example()
    publish(channel, event)
    consume_once(app.state.engine, settings)
    headers = auth(client)
    registered = register(client, intake(client, headers), headers).json()
    unavailable = replace(settings, rabbitmq_url="amqp://guest:guest@127.0.0.1:1/%2F", max_attempts=1)
    assert publish_pending(app.state.engine, unavailable) == 0
    delivery = client.get("/api/v1/deliveries?status=failed", headers=headers).json()["items"][0]
    retry = command(
        client,
        f"/deliveries/{delivery['event_id']}/retry",
        {"expected_revision": delivery["revision"]},
        headers,
    )
    assert retry.status_code == 200
    assert publish_pending(app.state.engine, settings) == 1
    method, _, body = channel.basic_get(queue, auto_ack=False)
    assert method is not None
    assert json.loads(body)["payload"]["assignment_id"] == registered["assignment"]["id"]
    channel.basic_ack(method.delivery_tag)


def test_unroutable_publication_remains_pending(app, client, broker):
    settings, channel, queue = broker
    event = example()
    publish(channel, event)
    consume_once(app.state.engine, settings)
    headers = auth(client)
    register(client, intake(client, headers), headers)
    channel.queue_unbind(queue=queue, exchange="w1.workforce", routing_key="assignment.registered")
    assert publish_pending(app.state.engine, settings) == 0
    with Session(app.state.engine) as session, session.begin():
        row = session.scalar(select(Outbox))
        assert row.status == "pending"
        assert row.last_error == "UnroutableError"
        row.next_attempt_at = now()
    channel.queue_bind(queue=queue, exchange="w1.workforce", routing_key="assignment.registered")
    assert publish_pending(app.state.engine, settings) == 1


@pytest.mark.parametrize("decision", ["apply", "keep"])
def test_review_result_delivered_to_hiring_queue_and_matches_shared_fixture(app, client, broker, decision):
    from tests.test_review import corrected

    settings, channel, _ = broker
    queue = channel.queue_declare(queue="", exclusive=True).method.queue
    channel.queue_bind(queue=queue, exchange="w1.workforce", routing_key="assignment.review-resolved")
    headers, first, correction, pending = corrected(app, client)
    action = "apply_correction" if decision == "apply" else "keep_existing"
    expected = json.loads((FIXTURES / "corrections.json").read_text(encoding="utf-8"))["alternatives"][action]
    body = {
        "expected_revision": pending["revision"],
        "expected_assignment_revision": 1,
        "action": action,
        "reason": expected["payload"]["reason"],
    }
    result = command(client, f"/intakes/{pending['id']}/resolve-correction", body, headers)
    assert result.status_code == 200
    assert publish_pending(app.state.engine, settings) == 2
    method, properties, raw = channel.basic_get(queue, auto_ack=False)
    assert method is not None and properties.delivery_mode == 2
    received = json.loads(raw)
    # Only runtime identities/timestamps differ from the independently authored shared fixture.
    expected.update(
        event_id=received["event_id"],
        aggregate_id=first["assignment"]["id"],
        correlation_id=correction["correlation_id"],
        occurred_at=received["occurred_at"],
    )
    expected["payload"].update(
        intake_id=pending["id"],
        source_event_id=correction["event_id"],
        employee_id=first["employee"]["id"],
        assignment_id=first["assignment"]["id"],
    )
    assert received == expected
    channel.basic_ack(method.delivery_tag)
