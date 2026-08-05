from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from .task import PredictionResult
from .transaction import Transaction


@dataclass
class PredictionHistoryEntry:
    """ Одна законченная задача: что планировалось, что вернулось, стоимость """

    task_id: UUID
    user_id: UUID
    model_version: str
    items: tuple[object, ...]
    result: PredictionResult
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PredictionHistory:
    """ In-memory история для демо """

    def __init__(self) -> None:
        self._entries: list[PredictionHistoryEntry] = []

    def add(self, entry: PredictionHistoryEntry) -> None:
        self._entries.append(entry)

    def for_user(self, user_id: UUID) -> list[PredictionHistoryEntry]:
        entries = [entry for entry in self._entries if entry.user_id == user_id]
        return sorted(entries, key=lambda entry: entry.created_at, reverse=True)

    def __len__(self) -> int:
        return len(self._entries)


class TransactionHistory:
    """ 
        Реестр каждой выполненной транзакции.

        Пользователи видят только свои операции, а администраторы проверяют все.
    """

    def __init__(self) -> None:
        self._transactions: list[Transaction] = []

    def add(self, transaction: Transaction) -> None:
        self._transactions.append(transaction)

    def for_user(self, user_id: UUID) -> list[Transaction]:
        txs = [tx for tx in self._transactions if tx.user.id == user_id]
        return sorted(txs, key=lambda tx: tx.created_at, reverse=True)

    def all(self) -> list[Transaction]:
        return sorted(self._transactions, key=lambda tx: tx.created_at, reverse=True)

    def __len__(self) -> int:
        return len(self._transactions)