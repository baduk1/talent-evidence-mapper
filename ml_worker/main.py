"""ML-воркер: слушает очередь RabbitMQ и обрабатывает ML-задачи.

Один издатель (REST API) - несколько таких воркеров. prefetch_count=1 +
ручной ack дают честный round-robin: кто освободился, тот и взял задачу.
"""
import json
import logging
import os
import socket
import time
from decimal import Decimal

import pika
from sqlmodel import Session

from tem.domain.enums import TaskStatus
from tem.domain.evidence import EvidenceItem, KeywordEvidenceClassifierModel
from tem.domain.exceptions import InsufficientBalanceError
from tem.infrastructure.db import crud
from tem.infrastructure.db.database import engine, init_db
from tem.infrastructure.db.models import MLModelORM
from tem.infrastructure.mq import QUEUE_NAME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

WORKER_ID = socket.gethostname()  # в docker это id контейнера - различим воркеров


def process_task(session: Session, message: dict) -> None:
    """Вся обработка одной задачи: валидация, списание, предикт, запись."""
    task_id = message["task_id"]
    task = crud.get_task(session, task_id)
    if task is None:
        logger.error(f"Task {task_id} not found in DB, skipping")
        return

    model_orm = session.get(MLModelORM, message["model_id"])
    if model_orm is None:
        crud.finish_task(session, task_id, TaskStatus.FAILED, Decimal("0"))
        return

    # Правила валидации и предсказания берём из домена, не дублируем.
    model = KeywordEvidenceClassifierModel(
        model_id=model_orm.id,
        name=model_orm.name,
        description="",
        version=model_orm.version,
        credit_cost=model_orm.credit_cost,
    )

    valid: list[tuple[int, EvidenceItem]] = []
    invalid_count = 0
    for index, item_dict in enumerate(message["items"]):
        item = EvidenceItem(**item_dict)
        if model.validate_input(item):
            invalid_count += 1
        else:
            valid.append((index, item))

    # Списываем только за валидные items. Не хватило средств - FAILED,
    # ничего не списано.
    cost = model_orm.credit_cost * len(valid)
    try:
        if cost > 0:
            crud.charge(session, task.user_id, cost, task_id=task_id)
    except InsufficientBalanceError:
        crud.finish_task(session, task_id, TaskStatus.FAILED, Decimal("0"))
        logger.info(f"Task {task_id} failed: insufficient balance")
        return

    for index, item in valid:
        mapping = model.predict(item)
        crud.create_prediction_record(
            session,
            task_id=task_id,
            item_index=index,
            title=item.title,
            primary_category=mapping.primary.category.value,
            confidence=mapping.primary.confidence,
            human_review_required=mapping.human_review_required,
            worker_id=WORKER_ID,
        )

    task_status = TaskStatus.COMPLETED if invalid_count == 0 else TaskStatus.PARTIALLY_COMPLETED
    crud.finish_task(session, task_id, task_status, cost)
    logger.info(f"Task {task_id} processed by {WORKER_ID}: {task_status.value}, charged {cost}")


def callback(ch, method, properties, body) -> None:
    try:
        message = json.loads(body)
        with Session(engine) as session:
            process_task(session, message)
            session.commit()
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("Failed to process message")
        # requeue=False - битое сообщение не зацикливаем
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    init_db()
    params = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        virtual_host="/",
        credentials=pika.PlainCredentials(username="guest", password="guest"),
        heartbeat=30,
        blocked_connection_timeout=2,
    )
    # RabbitMQ в docker поднимается не мгновенно - терпеливо дожидаемся.
    while True:
        try:
            connection = pika.BlockingConnection(params)
            break
        except pika.exceptions.AMQPConnectionError:
            logger.info("RabbitMQ is not ready yet, retrying in 3s...")
            time.sleep(3)

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME)
    channel.basic_qos(prefetch_count=1)  # честное распределение между воркерами
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback, auto_ack=False)

    logger.info(f"Worker {WORKER_ID} is waiting for messages. To exit, press Ctrl+C")
    channel.start_consuming()


if __name__ == "__main__":
    main()