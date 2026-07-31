from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generic
from uuid import UUID, uuid4

from .enums import TaskStatus
from .exceptions import InsufficientBalanceError
from .ml_model import InputT, MLModel, ResultT
from .transaction import DebitTransaction
from .user import User


@dataclass
class BatchItemError:
    item_index: int
    messages: list[str]


@dataclass
class PredictionResult(Generic[ResultT]):
    task_id: UUID
    predictions: list[ResultT]
    invalid_items: list[BatchItemError]
    credits_charged: Decimal
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_successful(self) -> bool:
        return bool(self.predictions)


class MLTask(Generic[InputT, ResultT]):
    """
        Жизненный цикл батч запроса. 

        Зависит от интерфейса MLModel, не от конкретной модели.
        Выполняет 2 платежных правила из курса: невалидные объекты возвращаются и никогда не меняюстся
        и дебит проходит только по обработанным объектам
    """

    def __init__(self, user: User, model: MLModel[InputT, ResultT], items: list[InputT]) -> None:
        self.id: UUID = uuid4()
        self.user = user
        self.model = model
        self._items = list(items)
        self.status = TaskStatus.CREATED
        self.created_at = datetime.now(timezone.utc)
        self.debit_transaction: DebitTransaction | None = None

    @property
    def items(self) -> tuple[InputT, ...]:
        return tuple(self._items)

    def estimated_cost(self) -> Decimal:
        return self.model.credit_cost * len(self._items)

    def validate(self) -> tuple[list[InputT], list[BatchItemError]]:
        self.status = TaskStatus.VALIDATING
        valid: list[InputT] = []
        errors: list[BatchItemError] = []
        for index, item in enumerate(self._items):
            item_errors = self.model.validate_input(item)
            if item_errors:
                errors.append(BatchItemError(index, item_errors))
            else:
                valid.append(item)
        return valid, errors


    def execute(self) -> PredictionResult[ResultT]:
        valid_items, errors = self.validate()
        cost = self.model.credit_cost * len(valid_items)
        if not self.user.can_afford(cost):
            self.status = TaskStatus.FAILED
            raise InsufficientBalanceError("Недостаточно средств для этой задачи")
        self.status = TaskStatus.PROCESSING
        predictions = [self.model.predict(item) for item in valid_items]
        if cost > 0:
            self.debit_transaction = DebitTransaction(self.user, cost, task_id=self.id)
            self.debit_transaction.apply()
        self,status = TaskStatus.COMPLETED if not errors else TaskStatus.PARTIALLY_COMPLETED
        return PredictionResult(self.id, predictions, errors, cost)
    
