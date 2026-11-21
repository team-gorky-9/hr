"""Транзакционный outbox-реле для гарантированной доставки requirements.approved."""
import argparse
from datetime import datetime, timedelta
import logging
import threading
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import load_settings
from ..db.base import utcnow
from ..db.models import OutboxEvent
from ..db.session import create_db_engine, create_session_factory
from .transport import BrokerPublishError, MessagePublisher, RabbitMQPublisher

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Читает pending-события из outbox_events, публикует их и применяет backoff."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        publisher: MessagePublisher,
        max_attempts: int = 5,
        base_backoff_sec: float = 2.0,
        poll_interval_sec: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._max_attempts = max(1, max_attempts)
        self._base_backoff_sec = max(0.0, base_backoff_sec)
        self._poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._wakeup_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._flush_lock = threading.Lock()

    @property
    def publisher(self) -> MessagePublisher:
        return self._publisher

    def wakeup(self) -> None:
        """Разбудить фоновый поток сразу после появления нового события в outbox."""
        self._wakeup_event.set()

    def start(self) -> None:
        """Запустить фоновый поток доставки, если poll_interval_sec > 0."""
        if self._poll_interval_sec <= 0 or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="requirements-outbox-relay",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Остановить фоновый поток доставки."""
        self._stop_event.set()
        self._wakeup_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.flush_once()
            except Exception:
                logger.exception("Outbox flush iteration failed")
            self._wakeup_event.wait(timeout=self._poll_interval_sec)
            self._wakeup_event.clear()

    def flush_once(
        self,
        *,
        now: datetime | None = None,
        batch_size: int = 50,
    ) -> int:
        """Попытаться отправить все готовые pending-события. Возвращает число отправленных."""
        with self._flush_lock:
            current_time = now or utcnow()
            sent_count = 0
            with self._session_factory() as session:
                event_ids = list(
                    session.scalars(
                        select(OutboxEvent.event_id)
                        .where(
                            OutboxEvent.status == "pending",
                            OutboxEvent.next_attempt_at <= current_time,
                        )
                        .order_by(OutboxEvent.created_at.asc(), OutboxEvent.event_id.asc())
                        .limit(batch_size)
                    )
                )
            for event_id in event_ids:
                if self._deliver_single(event_id, current_time=now or utcnow()):
                    sent_count += 1
            return sent_count

    def deliver_event_by_id(self, event_id: uuid.UUID, *, now: datetime | None = None) -> bool:
        """Немедленно попытаться доставить конкретное событие."""
        with self._flush_lock:
            return self._deliver_single(event_id, current_time=now or utcnow())

    def _deliver_single(self, event_id: uuid.UUID, *, current_time: datetime) -> bool:
        with self._session_factory() as session:
            event = session.get(OutboxEvent, event_id)
            if event is None or event.status != "pending":
                return False
            try:
                self._publisher.publish(
                    exchange=event.exchange,
                    routing_key=event.routing_key,
                    envelope=event.envelope,
                )
            except (BrokerPublishError, Exception) as exc:
                event.attempts += 1
                event.attempts_since_reset += 1
                event.last_error = str(exc)[:500]
                event.updated_at = current_time
                if event.attempts_since_reset >= self._max_attempts:
                    event.status = "failed"
                else:
                    delay_sec = self._base_backoff_sec * (2 ** (event.attempts_since_reset - 1))
                    event.next_attempt_at = current_time + timedelta(seconds=delay_sec)
                session.commit()
                return False

            event.status = "sent"
            event.attempts += 1
            event.attempts_since_reset += 1
            event.last_error = None
            event.sent_at = current_time
            event.updated_at = current_time
            session.commit()
            return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Outbox relay для сервиса требований")
    parser.add_argument("--once", action="store_true", help="Выполнить один цикл отправки и выйти")
    args = parser.parse_args(argv)

    settings = load_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    publisher = RabbitMQPublisher(settings.rabbitmq_url)
    relay = OutboxRelay(
        session_factory=session_factory,
        publisher=publisher,
        max_attempts=settings.outbox_max_attempts,
        base_backoff_sec=settings.outbox_base_backoff_sec,
        poll_interval_sec=settings.outbox_poll_interval_sec,
    )
    try:
        if args.once:
            sent = relay.flush_once()
            print(f"outbox flushed: sent={sent}")
            return 0
        while True:
            relay.flush_once()
            time.sleep(max(0.2, settings.outbox_poll_interval_sec))
    except KeyboardInterrupt:
        return 0
    finally:
        publisher.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
