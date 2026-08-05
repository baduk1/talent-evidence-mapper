from decimal import Decimal

from tem.domain.enums import TransactionType
from tem.domain.transaction import CreditTransaction, DebitTransaction
from tem.domain.user import User


def test_credit_transaction_applies():
    user = User(email="a@b.com", _password_hash="h")
    tx = CreditTransaction(user, Decimal("20"))
    tx.apply()
    assert user.balance.amount == Decimal("20")
    assert tx.type == TransactionType.CREDIT


def test_debit_transaction_applies():
    user = User(email="a@b.com", _password_hash="h")
    CreditTransaction(user, Decimal("20")).apply()
    tx = DebitTransaction(user, Decimal("5"))
    tx.apply()
    assert user.balance.amount == Decimal("15")
    assert tx.type == TransactionType.DEBIT


def test_transactions_are_polymorphic():
    user = User(email="a@b.com", _password_hash="h")
    ledger = [
        CreditTransaction(user, Decimal("10")),
        CreditTransaction(user, Decimal("5")),
        DebitTransaction(user, Decimal("3")),
    ]
    for tx in ledger:
        tx.apply()
    assert user.balance.amount == Decimal("12")


def test_transaction_carries_optional_task_link():
    user = User(email="a@b.com", _password_hash="h")
    tx = CreditTransaction(user, Decimal("10"))
    assert tx.task_id is None