from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Numeric
from sqlmodel import Field, SQLModel

from ...domain.enums import TaskStatus, TransactionType, UserRole


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserORM(SQLModel, table=True):
    """Как доменный User хранится в таблице. Правила живут в домене,
    здесь только хранение."""

    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    email: str = Field(unique=True, index=True, max_length=320)
    password_hash: str = Field(max_length=255)
    role: UserRole = Field(default=UserRole.USER, sa_column=Column(SAEnum(UserRole)))
    balance: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2)))


class MLModelORM(SQLModel, table=True):
    __tablename__ = "ml_models"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    name: str = Field(max_length=120)
    version: str = Field(max_length=40)
    credit_cost: Decimal = Field(default=Decimal("1"), sa_column=Column(Numeric(18, 2)))
    active: bool = Field(default=True)


class TransactionORM(SQLModel, table=True):
    __tablename__ = "transactions"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", max_length=36)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 2)))
    type: TransactionType = Field(sa_column=Column(SAEnum(TransactionType)))
    task_id: str | None = Field(default=None, max_length=36)
    created_at: datetime = Field(default_factory=_now)


class PredictionTaskORM(SQLModel, table=True):
    __tablename__ = "prediction_tasks"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", max_length=36)
    model_id: str = Field(foreign_key="ml_models.id", max_length=36)
    status: TaskStatus = Field(default=TaskStatus.CREATED, sa_column=Column(SAEnum(TaskStatus)))
    credits_charged: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2)))
    created_at: datetime = Field(default_factory=_now)



class PredictionRecordORM(SQLModel, table=True):
    """Результат обработки одного item'а воркером."""

    __tablename__ = "prediction_records"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    task_id: str = Field(foreign_key="prediction_tasks.id", max_length=36)
    item_index: int = Field(default=0)
    title: str = Field(max_length=255)
    primary_category: str = Field(max_length=64)
    confidence: float = Field(default=0.0)
    human_review_required: bool = Field(default=True)
    worker_id: str = Field(max_length=64)  # кто обработал - видно распределение
    created_at: datetime = Field(default_factory=_now)