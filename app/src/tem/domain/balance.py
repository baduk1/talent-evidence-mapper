from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

from .exceptions import InsufficientBalanceError, InvalidAmountError


@dataclass
class Balance:
    """
    Деньги пользователя в кредитах.

    Вынесено из User по замечанию куратора: юзер отвечает за то, кто он такой
    (почта, пароль, роль), а не за хранение и правила денег.
    Все инварианты живут здесь: сумма не уходит в минус,
    пополнение и списание только положительными суммами.
    Сумму нельзя поменять напрямую - только через credit() и debit().
    """

    _amount: Decimal = Decimal("0")

    @property
    def amount(self) -> Decimal:
        return self._amount

    def can_afford(self, value: Decimal) -> bool:
        return value >= 0 and self._amount >= value

    def credit(self, value: Decimal) -> None:
        if value <= 0:
            raise InvalidAmountError("Пополнение должно быть положительным")
        self._amount += value

    def debit(self, value: Decimal) -> None:
        if value <= 0:
            raise InvalidAmountError("Списание должно быть положительным")
        if not self.can_afford(value):
            raise InsufficientBalanceError("Недостаточно средств")
        self._amount -= value
