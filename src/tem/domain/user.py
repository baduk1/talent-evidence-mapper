from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from .balance import Balance
from .enums import UserRole


@dataclass
class User:
    """
    Пользователь сервиса: кто он такой (почта, пароль, роль).

    Деньги - не его зона ответственности, они в отдельной сущности Balance.
    Методы credit()/debit()/can_afford() оставлены как тонкие делегаты,
    чтобы вызывающий код (транзакции, MLTask) не переписывать.
    """
    email: str
    _password_hash: str
    id: UUID = field(default_factory=uuid4)
    role: UserRole = UserRole.USER
    balance: Balance = field(default_factory=Balance)

    def __post_init__(self) -> None:
        if "@" not in self.email:
            raise ValueError("email должен содержать '@'")

    def verify_password(self, password_hash: str) -> bool:
        return self._password_hash == password_hash

    def can_afford(self, amount: Decimal) -> bool:
        return self.balance.can_afford(amount)

    def credit(self, amount: Decimal) -> None:
        self.balance.credit(amount)

    def debit(self, amount: Decimal) -> None:
        self.balance.debit(amount)


@dataclass
class Administrator(User):
    """
    Наследуемся от User с админ действиями.
    Принцип наследования ООП
    """

    role: UserRole = UserRole.ADMIN

    def approve_top_up(self, user: User, amount: Decimal) -> None:
        user.credit(amount)
