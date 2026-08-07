from decimal import Decimal

from sqlmodel import Session, select

from ...domain.enums import TransactionType, UserRole
from ...domain.exceptions import InsufficientBalanceError, InvalidAmountError
from .models import MLModelORM, TransactionORM, UserORM


def create_user(
    session: Session,
    email: str,
    password_hash: str,
    role: UserRole = UserRole.USER,
    balance: Decimal = Decimal("0"),
) -> UserORM:
    user = UserORM(email=email, password_hash=password_hash, role=role, balance=balance)
    session.add(user)
    session.flush()
    return user


def get_user_by_id(session: Session, user_id: str) -> UserORM | None:
    return session.get(UserORM, user_id)


def get_user_by_email(session: Session, email: str) -> UserORM | None:
    return session.exec(select(UserORM).where(UserORM.email == email)).first()


def add_model(
    session: Session,
    name: str,
    version: str,
    credit_cost: Decimal = Decimal("1"),
    active: bool = True,
) -> MLModelORM:
    model = MLModelORM(name=name, version=version, credit_cost=credit_cost, active=active)
    session.add(model)
    session.flush()
    return model


def list_active_models(session: Session) -> list[MLModelORM]:
    return list(session.exec(select(MLModelORM).where(MLModelORM.active.is_(True))))


def add_transaction(
    session: Session,
    user_id: str,
    amount: Decimal,
    tx_type: TransactionType,
    task_id: str | None = None,
) -> TransactionORM:
    tx = TransactionORM(user_id=user_id, amount=amount, type=tx_type, task_id=task_id)
    session.add(tx)
    session.flush()
    return tx


def list_transactions_for_user(session: Session, user_id: str) -> list[TransactionORM]:
    stmt = (
        select(TransactionORM)
        .where(TransactionORM.user_id == user_id)
        .order_by(TransactionORM.created_at.desc())
    )
    return list(session.exec(stmt))


def top_up(session: Session, user_id: str, amount: Decimal) -> Decimal:
    """Пополнение: баланс и запись в истории меняются вместе, одной сессией."""
    if amount <= 0:
        raise InvalidAmountError("Пополнение должно быть положительным")
    user = get_user_by_id(session, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    user.balance = user.balance + amount
    add_transaction(session, user_id, amount, TransactionType.CREDIT)
    session.flush()
    return user.balance


def charge(session: Session, user_id: str, amount: Decimal, task_id: str | None = None) -> Decimal:
    """Списание: сначала проверка баланса, потом списание и запись в историю."""
    if amount <= 0:
        raise InvalidAmountError("Списание должно быть положительным")
    user = get_user_by_id(session, user_id)
    if user is None:
        raise ValueError("Пользователь не найден")
    if user.balance < amount:
        raise InsufficientBalanceError("Недостаточно средств")
    user.balance = user.balance - amount
    add_transaction(session, user_id, amount, TransactionType.DEBIT, task_id=task_id)
    session.flush()
    return user.balance