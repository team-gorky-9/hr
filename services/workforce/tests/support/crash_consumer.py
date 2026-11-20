"""Exercise the real commit-before-ack crash window in an expendable subprocess."""

import json
import os

from workforce.config import Settings
from workforce.database import make_engine
from workforce.events import receive_event
from workforce.worker import QUEUE, connect, topology


def main():
    settings = Settings()
    connection = connect(settings)
    channel = connection.channel()
    topology(channel)
    method, _, body = channel.basic_get(queue=QUEUE, auto_ack=False)
    if method is None:
        raise RuntimeError("Expected a message to exercise commit before ack")
    engine = make_engine(settings.database_url)
    receive_event(engine, json.loads(body))
    # Intentional hard exit: the real broker must requeue this unacknowledged delivery.
    os._exit(17)


if __name__ == "__main__":
    main()
