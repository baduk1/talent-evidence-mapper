"""Издатель сообщений в RabbitMQ (pika, как на лекции)."""
import json
import os
from datetime import datetime, timezone

import pika

QUEUE_NAME = "ml_task_queue"


def _connection_params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        virtual_host="/",
        credentials=pika.PlainCredentials(username="guest", password="guest"),
        heartbeat=30,
        blocked_connection_timeout=2,
    )


def send_task(message: dict) -> None:
    """Опубликовать ML-задачу в очередь. Одно сообщение = одна задача."""
    message = {**message, "timestamp": datetime.now(timezone.utc).isoformat()}
    connection = pika.BlockingConnection(_connection_params())
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME)
    channel.basic_publish(
        exchange="",  # default exchange, как требует задание
        routing_key=QUEUE_NAME,
        body=json.dumps(message),
    )
    connection.close()