from decimal import Decimal

import pytest

from tem.domain.exceptions import InsufficientBalanceError
from tem.infrastructure.db import crud
from tem.infrastructure.db.seed import seed


def test_create_and_load_user(session):
    user = crud.create_user(session, "a@b.com", "h", balance=Decimal("5"))
    session.commit()
    loaded = crud.get_user_by_email(session, "a@b.com")
    assert loaded is not None
    assert loaded.id == user.id
    assert loaded.balance == Decimal("5")


def test_top_up_and_charge(session):
    user = crud.create_user(session, "a@b.com", "h")
    session.flush()
    crud.top_up(session, user.id, Decimal("10"))
    assert crud.get_user_by_id(session, user.id).balance == Decimal("10")
    crud.charge(session, user.id, Decimal("4"))
    assert crud.get_user_by_id(session, user.id).balance == Decimal("6")


def test_charge_beyond_balance_raises(session):
    user = crud.create_user(session, "a@b.com", "h", balance=Decimal("2"))
    session.flush()
    with pytest.raises(InsufficientBalanceError):
        crud.charge(session, user.id, Decimal("5"))
    assert crud.get_user_by_id(session, user.id).balance == Decimal("2")


def test_history_present_and_ordered(session):
    user = crud.create_user(session, "a@b.com", "h")
    session.flush()
    crud.top_up(session, user.id, Decimal("10"))
    crud.charge(session, user.id, Decimal("3"))
    history = crud.list_transactions_for_user(session, user.id)
    assert len(history) == 2
    assert history[0].created_at >= history[1].created_at


def test_seed_is_idempotent(session):
    seed(session)
    session.flush()
    seed(session)
    session.flush()
    assert crud.get_user_by_email(session, "user@example.com") is not None
    assert len(crud.list_active_models(session)) == 2