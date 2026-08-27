from decimal import Decimal

from sqlmodel import Session, select

from ...domain.enums import TransactionType, UserRole
from ...domain.exceptions import InsufficientBalanceError, InvalidAmountError
from .models import MLModelORM, TransactionORM, UserORM, PredictionTaskORM, TaskStatus, PredictionRecordORM, BatchItemErrorORM


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


def get_default_model(session: Session) -> MLModelORM | None:
    """Модель для новых задач: боевая zero-shot (mDeBERTa), иначе любая
    активная. Порядок строк в БД не гарантирован, поэтому выбираем по имени."""
    models = list_active_models(session)
    for model in models:
        if "mdeberta" in model.name.lower():
            return model
    return next(iter(models), None)


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


def list_users(session: Session) -> list[UserORM]:
    """Все пользователи для админ-панели."""
    return list(session.exec(select(UserORM).order_by(UserORM.email)))


def list_all_transactions(session: Session, limit: int = 300) -> list[TransactionORM]:
    """Все транзакции системы для админки, новые сверху."""
    stmt = select(TransactionORM).order_by(TransactionORM.created_at.desc()).limit(limit)
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


def create_task(session: Session, user_id: str, model_id: str) -> PredictionTaskORM:
    task = PredictionTaskORM(user_id=user_id, model_id=model_id)
    session.add(task)
    session.flush()
    return task


def finish_task(
    session: Session,
    task_id: str,
    status: TaskStatus,
    credits_charged: Decimal,
) -> PredictionTaskORM:
    task = session.get(PredictionTaskORM, task_id)
    task.status = status
    task.credits_charged = credits_charged
    session.flush()
    return task


def list_tasks_for_user(session: Session, user_id: str) -> list[PredictionTaskORM]:
    stmt = (
        select(PredictionTaskORM)
        .where(PredictionTaskORM.user_id == user_id)
        .order_by(PredictionTaskORM.created_at.desc())
    )
    return list(session.exec(stmt))


def get_task(session: Session, task_id: str) -> PredictionTaskORM | None:
    return session.get(PredictionTaskORM, task_id)


def create_prediction_record(
    session: Session,
    task_id: str,
    item_index: int,
    title: str,
    primary_category: str,
    confidence: float,
    human_review_required: bool,
    worker_id: str,
    secondary: list | None = None,
    missing_information: list | None = None,
) -> PredictionRecordORM:
    record = PredictionRecordORM(
        task_id=task_id,
        item_index=item_index,
        title=title,
        primary_category=primary_category,
        confidence=confidence,
        human_review_required=human_review_required,
        worker_id=worker_id,
        secondary=secondary or [],
        missing_information=missing_information or [],
    )
    session.add(record)
    session.flush()
    return record


def list_records_for_task(session: Session, task_id: str) -> list[PredictionRecordORM]:
    stmt = (
        select(PredictionRecordORM)
        .where(PredictionRecordORM.task_id == task_id)
        .order_by(PredictionRecordORM.item_index)
    )
    return list(session.exec(stmt))


def create_item_error(
    session: Session, task_id: str, item_index: int, messages: str
) -> BatchItemErrorORM:
    item_error = BatchItemErrorORM(task_id=task_id, item_index=item_index, messages=messages)
    session.add(item_error)
    session.flush()
    return item_error


def list_item_errors_for_task(session: Session, task_id: str) -> list[BatchItemErrorORM]:
    stmt = (
        select(BatchItemErrorORM)
        .where(BatchItemErrorORM.task_id == task_id)
        .order_by(BatchItemErrorORM.item_index)
    )
    return list(session.exec(stmt))