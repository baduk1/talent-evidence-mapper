from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from .enums import TransactionType
from .user import User


class Transaction(ABC):
    """
    Абстрасктная финансовая опрерация на балансе пользователя
    
    Точные подклассы выполняют apply() иначе, но через тотже интерфейс.
    Это имплементация полиморфизма ООП из лекции
    """

    def __init__(self, user:User, amount: Decimal, task_id: UUID | None = None) -> None:
        self.id: UUID = uuid4()
        self.user = user
        self.amount = amount
        self.task_id = task_id
        self.created_at = datetime.now(timezone.utc)


    @property
    @abstractmethod
    def type(self) -> TransactionType:
        ...


    @abstractmethod
    def apply(self) -> None:
        ...


class CreditTransaction(Transaction):
    @property
    def type(self) -> TransactionType:
        return TransactionType.CREDIT

    def apply(self) -> None:
        self.user.credit(self.amount)


class DebitTransaction(Transaction):
    @property
    def type(self) -> TransactionType:
        return TransactionType.DEBIT

    def apply(self) -> None:
        self.user.debit(self.amount)
