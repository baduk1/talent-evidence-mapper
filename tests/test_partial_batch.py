from decimal import Decimal

import pytest

from tem.domain.enums import TaskStatus, TransactionType
from tem.domain.evidence import EvidenceItem, KeywordEvidenceClassifierModel
from tem.domain.exceptions import InsufficientBalanceError
from tem.domain.task import MLTask
from tem.domain.user import User


def make_setup(balance: str = "10"):
    user = User(email="a@b.com", _password_hash="h")
    if Decimal(balance) > 0:
        user.credit(Decimal(balance))
    model = KeywordEvidenceClassifierModel(
        "kw-1", "Keyword", "Offline keyword baseline", "0.1", Decimal("1")
    )
    return user, model


def valid_item(index: int = 0) -> EvidenceItem:
    return EvidenceItem(
        title=f"Item {index}",
        description=(
            "I created and maintain an open source library with measurable impact "
            "and many users"
        ),
    )


def invalid_item() -> EvidenceItem:
    return EvidenceItem(title="", description="short")


def test_execute_charges_only_valid_items():
    user, model = make_setup("10")
    task = MLTask(user, model, [valid_item(1), invalid_item(), valid_item(2)])
    result = task.execute()
    assert result.credits_charged == Decimal("2")
    assert user.balance == Decimal("8")
    assert task.status == TaskStatus.PARTIALLY_COMPLETED


def test_execute_records_debit_transaction_linked_to_task():
    user, model = make_setup("10")
    task = MLTask(user, model, [valid_item(1)])
    task.execute()
    assert task.debit_transaction is not None
    assert task.debit_transaction.type == TransactionType.DEBIT
    assert task.debit_transaction.task_id == task.id


def test_clean_batch_completes_fully():
    user, model = make_setup("10")
    task = MLTask(user, model, [valid_item(1)])
    result = task.execute()
    assert task.status == TaskStatus.COMPLETED
    assert result.is_successful
    assert result.invalid_items == []


def test_execute_fails_without_charging_when_balance_is_low():
    user, model = make_setup("1")
    task = MLTask(user, model, [valid_item(1), valid_item(2)])
    with pytest.raises(InsufficientBalanceError):
        task.execute()
    assert task.status == TaskStatus.FAILED
    assert user.balance == Decimal("1")
    assert task.debit_transaction is None