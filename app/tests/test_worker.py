"""Логика воркера без RabbitMQ: process_task напрямую на sqlite in-memory."""
from decimal import Decimal

import pytest
from sqlmodel import SQLModel, Session, create_engine

from tem.domain.enums import TaskStatus, TransactionType
from tem.infrastructure.db import crud
from tem.infrastructure.db.seed import seed
from tem.infrastructure.db.models import MLModelORM

import sys
sys.path.insert(0, "../ml_worker")  # воркер живёт отдельным сервисом
from main import process_task  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed(session)
        session.commit()
        yield session


def make_message(session, balance: str, items: list[dict]) -> dict:
    user = crud.create_user(session, "w@b.com", "h", balance=Decimal(balance))
    model = crud.list_active_models(session)[0]
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