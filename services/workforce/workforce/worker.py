import json
import logging
import signal
from datetime import timedelta
from threading import Event

import pika
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from workforce.config import Settings
from workforce.database import make_engine
from workforce.domain import changed
from workforce.events import InvalidEvent, receive_event
from workforce.models import Outbox, now

log = logging.getLogger(__name__)
QUEUE = "w1.workforce.employment.ready"
DEAD_QUEUE = "w1.workforce.dead"


def connect(settings):
    parameters = pika.URLParameters(settings.rabbitmq_url)
    parameters.connection_attempts = 1
    parameters.socket_timeout = 2
    parameters.stack_timeout = 4
    parameters.blocked_connection_timeout = 3
    parameters.heartbeat = 30
    return pika.BlockingConnection(parameters)


def broker_available(settings):
    try:
        connection = connect(settings)
        connection.close()
        return True
    except (pika.exceptions.AMQPError, OSError):
        return False


def topology(channel):
    channel.exchange_declare(exchange="w1.hiring", exchange_type="topic", durable=True)
    channel.exchange_declare(exchange="w1.workforce", exchange_type="topic", durable=True)
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.queue_bind(queue=QUEUE, exchange="w1.hiring", routing_key="employment.ready")
    channel.queue_declare(queue=DEAD_QUEUE, durable=True)
    channel.confirm_delivery()


def publish_pending(engine, settings):
    count = 0
    # Row lock keeps concurrent workers from publishing the same pending row at once.
    # A crash after confirm still permits redelivery: event_id is stable and inbox deduplicates it.
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(Outbox)
            .where(Outbox.status == "pending", Outbox.next_attempt_at <= now())
            .order_by(Outbox.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        )
        for row in rows:
            connection = None
            row.attempts += 1
            try:
                connection = connect(settings)
                channel = connection.channel()
                channel.exchange_declare(exchange="w1.workforce", exchange_type="topic", durable=True)
                channel.confirm_delivery()
                channel.basic_publish(
                    exchange="w1.workforce",
                    routing_key=row.event_type,
                    mandatory=True,
                    body=json.dumps(row.envelope, ensure_ascii=False).encode(),
                    properties=pika.BasicProperties(
                        content_type="application/json", delivery_mode=2, message_id=row.event_id
                    ),
                )
                row.status, row.last_error = "sent", None
                count += 1
            except (pika.exceptions.AMQPError, OSError) as exc:
                row.last_error = type(exc).__name__
                row.status = "failed" if row.attempts >= settings.max_attempts else "pending"
                row.next_attempt_at = now() + timedelta(
                    seconds=min(300, settings.retry_seconds * 2 ** (row.attempts - 1))
                )
                log.warning("Delivery deferred event_id=%s error=%s", row.event_id, type(exc).__name__)
            finally:
                if connection and connection.is_open:
                    try:
                        connection.close()
                    except pika.exceptions.AMQPError as exc:
                        log.warning("Broker close failed: %s", type(exc).__name__)
            changed(row)
    return count


def consume_once(engine, settings, limit=20):
    connection = connect(settings)
    count = 0
    try:
        channel = connection.channel()
        topology(channel)
        for _ in range(limit):
            method, properties, body = channel.basic_get(queue=QUEUE, auto_ack=False)
            if method is None:
                break
            try:
                if properties.content_type != "application/json":
                    raise InvalidEvent("INVALID_CONTENT_TYPE")
                receive_event(engine, json.loads(body))
            except (InvalidEvent, ValueError, UnicodeError) as exc:
                reason = str(exc) if isinstance(exc, InvalidEvent) else "INVALID_JSON"
                channel.basic_publish(
                    exchange="",
                    routing_key=DEAD_QUEUE,
                    mandatory=True,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=2, content_type="application/json", headers={"reason": reason}
                    ),
                )
                channel.basic_ack(method.delivery_tag)
            except OperationalError:
                channel.basic_nack(method.delivery_tag, requeue=True)
                raise
            else:
                # receive_event has committed both intake and inbox before acknowledging.
                channel.basic_ack(method.delivery_tag)
            count += 1
        return count
    finally:
        if connection.is_open:
            connection.close()


def main():
    logging.basicConfig(level=logging.INFO)
    # Pika's connection exceptions can contain endpoints; expose only sanitized types above.
    logging.getLogger("pika").setLevel(logging.CRITICAL)
    settings = Settings()
    engine = make_engine(settings.database_url)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        try:
            consume_once(engine, settings)
        except (pika.exceptions.AMQPError, OSError, OperationalError) as exc:
            log.warning("Intake polling deferred: %s", type(exc).__name__)
        try:
            publish_pending(engine, settings)
        except OperationalError as exc:
            log.warning("Outbox polling deferred: %s", type(exc).__name__)
        stop.wait(settings.poll_seconds)
    engine.dispose()


if __name__ == "__main__":
    main()
