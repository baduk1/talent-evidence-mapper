from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
ResultT = TypeVar("ResultT")

class MLModel(ABC, Generic[InputT, ResultT]):
    """
    Абстрактный контракт для любой модели МО

    Конкретную модель внедрю позже в курсе
    """

    def __init__(
        self,
        model_id: str,
        name: str,
        description: str,
        version: str,
        credit_cost: Decimal,
    ) -> None:
        self._model_id = model_id
        self._name = name
        self._description = description
        self._version = version
        self._credit_cost = credit_cost



    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def version(self) -> str:
        return self._version

    @property
    def verscredit_cost(self) -> Decimal:
        return self._credit_cost

    @abstractmethod
    def validate_input(self, item: InputT) -> list[str]:
        """ Вернет ошибки валидации, иначе все валидно """

    @abstractmethod
    def predict(self, item: InputT) -> ResultT:
        """ Делает 1 предсказание для 1 валидного объекта """