import argparse
import json
from uuid import uuid4

import pika

from workforce.config import Settings
from workforce.worker import connect, topology


def publish(channel, event, repeat=1):
    for _ in range(repeat):
        channel.basic_publish(
            exchange="w1.hiring",
            routing_key="employment.ready",
            mandatory=True,
            body=json.dumps(event, ensure_ascii=False).encode(),
            properties=pika.BasicProperties(
                content_type="application/json", delivery_mode=2, message_id=event["event_id"]
            ),
        )


def main():
    parser = argparse.ArgumentParser(description="Publish the shared synthetic employment.ready fixture")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--foreign", action="store_true")
    parser.add_argument("--prepare-receiver", action="store_true")
    parser.add_argument("--read-result", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    connection = connect(settings)
    try:
        channel = connection.channel()
        topology(channel)
        queue = "w1.hiring.assignment.registered"
        channel.queue_declare(queue=queue, durable=True)
        channel.queue_bind(queue=queue, exchange="w1.workforce", routing_key="assignment.registered")
        if args.prepare_receiver:
            print(json.dumps({"receiver": queue}))
            return
        if args.read_result:
            method, _, body = channel.basic_get(queue=queue, auto_ack=False)
            if method:
                print(body.decode())
                channel.basic_ack(method.delivery_tag)
            else:
                print(json.dumps({"status": "waiting"}))
            return
        event = json.loads((settings.fixture_dir / "events.json").read_text(encoding="utf-8"))["events"][0]
        if args.foreign:
            event["event_id"] = str(uuid4())
            event["organization_id"] = "00000000-0000-4000-8000-000000000002"
        publish(channel, event, args.repeat)
        print(
            json.dumps({"event_id": event["event_id"], "publications": args.repeat, "foreign": args.foreign})
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
