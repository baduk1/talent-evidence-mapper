from decimal import Decimal

import pytest
from tem.domain.enums import UserRole
from tem.domain.exceptions import InsufficientBalanceError, InvalidAmountError
from tem.domain.user import Administrator, User


def make_user(balance: str = "0") -> User:
    user = User(email="a@b.com", _password_hash="h")
    if Decimal(balance) > 0:
        user.credit(Decimal(balance))
    return user


def test_new_user_starts_with_zero_balance():
    user = User(email="a@b.com", _password_hash="h")
    assert user.balance.amount == Decimal("0")
    assert user.role == UserRole.USER


def test_credit_increases_balance():
    user = make_user()
    user.credit(Decimal("10"))
    assert user.balance.amount == Decimal("10")


def test_debit_decreases_balance():
    user = make_user("10")
    user.debit(Decimal("4"))
    assert user.balance.amount == Decimal("6")


def test_debit_beyond_balance_raises():
    user = make_user("3")
    with pytest.raises(InsufficientBalanceError):
        user.debit(Decimal("5"))


def test_credit_rejects_non_positive_amount():
    user = make_user()
    with pytest.raises(InvalidAmountError):
        user.credit(Decimal("0"))


def test_balance_amount_is_not_settable_directly():
    user = make_user("5")
    with pytest.raises(AttributeError):
        user.balance.amount = Decimal("100")


def test_verify_password():
    user = User(email="a@b.com", _password_hash='h')
    assert user.verify_password("h")
    assert not user.verify_password('wrong')
    

def test_administrator_approves_top_up():
    admin = Administrator(email="admin@b.com", _password_hash="h")
    user = make_user()
    assert admin.role == UserRole.ADMIN
    admin.approve_top_up(user, Decimal("7"))
    assert user.balance.amount == Decimal("7")

    