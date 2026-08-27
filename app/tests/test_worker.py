"""Логика воркера без RabbitMQ: process_task напрямую на sqlite in-memory."""
from decimal import Decimal

from tem.domain.enums import TaskStatus, TransactionType
from tem.infrastructure.db import crud

import sys
sys.path.insert(0, "../ml_worker")  # воркер живёт отдельным сервисом
from main import process_task  # noqa: E402


def make_message(session, balance: str, items: list[dict]) -> dict:
    user = crud.create_user(session, "w@b.com", "h", balance=Decimal(balance))
    model = crud.get_default_model(session)
    task = crud.create_task(session, user.id, model.id)
    session.flush()
    return {
        "task_id": task.id,
        "user_id": user.id,
        "model_id": model.id,
        "items": items,
    }


def valid_item(title="OSS") -> dict:
    return {
        "title": title,
        "description": (
            "I created and maintain an open source library with measurable impact "
            "and many users"
        ),
        "evidence_type": None,
        "source_url": None,
        "metrics": {},
    }


def test_worker_processes_task_and_charges(session):
    message = make_message(session, "10", [valid_item()])
    process_task(session, message)
    session.commit()

    task = crud.get_task(session, message["task_id"])
    assert task.status == TaskStatus.COMPLETED
    assert task.credits_charged == Decimal("1")

    records = crud.list_records_for_task(session, message["task_id"])
    assert len(records) == 1
    assert records[0].primary_category
    assert records[0].worker_id  # видно, кто обработал
    assert len(records[0].secondary) == 2  # запасные категории сохранены
    assert len(records[0].missing_information) == 2  # нет метрик и URL

    user = crud.get_user_by_id(session, message["user_id"])
    assert user.balance == Decimal("9")
    txs = crud.list_transactions_for_user(session, user.id)
    assert txs[0].type == TransactionType.DEBIT
    assert txs[0].task_id == task.id


def test_worker_fails_task_when_balance_is_low(session):
    message = make_message(session, "1", [valid_item("One"), valid_item("Two")])
    process_task(session, message)
    session.commit()

    task = crud.get_task(session, message["task_id"])
    assert task.status == TaskStatus.FAILED
    assert task.credits_charged == 0
    assert crud.list_records_for_task(session, message["task_id"]) == []
    assert crud.get_user_by_id(session, message["user_id"]).balance == Decimal("1")


def test_worker_marks_partial_batch_and_charges_only_valid(session):
    message = make_message(session, "10", [valid_item(), {"title": "", "description": "short"}])
    process_task(session, message)
    session.commit()

    task = crud.get_task(session, message["task_id"])
    assert task.status == TaskStatus.PARTIALLY_COMPLETED
    assert task.credits_charged == Decimal("1")
    assert len(crud.list_records_for_task(session, message["task_id"])) == 1

    # Причина отклонения сохранена - её покажет кабинет и API
    errors = crud.list_item_errors_for_task(session, message["task_id"])
    assert len(errors) == 1
    assert errors[0].item_index == 1
    assert "title is required" in errors[0].messages



def test_worker_all_invalid_batch_charges_nothing(session):
    message = make_message(session, "10", [{"title": "", "description": "short"}])
    process_task(session, message)
    session.commit()

    task = crud.get_task(session, message["task_id"])
    assert task.status == TaskStatus.PARTIALLY_COMPLETED
    assert task.credits_charged == 0

    # Ни одной транзакции списания не появилось
    txs = crud.list_transactions_for_user(session, message["user_id"])
    assert [tx for tx in txs if tx.type == TransactionType.DEBIT] == []

    # Причина отклонения сохранена
    assert len(crud.list_item_errors_for_task(session, message["task_id"])) == 1