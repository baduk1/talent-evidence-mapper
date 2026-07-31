from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4
from .enums import UserRole
from .exceptions import InsufficientBalanceError, InvalidAmountError


@dataclass
class User:
    """
    Владелец баланса и ML запросов. 
    Баланс не мутирует напрямую, только через credit() и debit().
    То есть это реализация инкапсуляции из лекции. 
    """
    email: str
    _password_hash: str
    id: UUID = field(default_factory=uuid4)
    role: UserRole = UserRole.USER
    _balance: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if "@" not in self.email:
            raise ValueError("email должен содержать '@'")

    @property
    def balance(self) -> Decimal:
        return self._balance

    def verify_password(self, password_hash: str) -> bool:
        return self._password_hash == password_hash

    def can_afford(self, amount: Decimal) -> bool:
        return amount >= 0 and self._balance >= amount

    def credit(self, amount: Decimal) -> None:
        if amount <= 0:
            raise InvalidAmountError("Баланс должен быть положительным")
        self._balance += amount

    def debit(self, amount: Decimal) -> None:
        if amount <= 0:
            raise InvalidAmountError("Баланс должен быть положительным")
        if not self.can_afford(amount):
            raise InsufficientBalanceError('Недостаточно средств')
        self._balance -= amount


@dataclass
class Administrator(User):
    """
    Наследуемся от User с админ действиями. 
    Принцип наследования ООП
    """

    rols: UserRole = UserRole.ADMIN

    def approve_top_up(self, user: User, amount: Decimal) -> None:
        user.credit(amount)
        

