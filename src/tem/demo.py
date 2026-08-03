from __future__ import annotations

from decimal import Decimal

from tem.domain.evidence import EvidenceItem, KeywordEvidenceClassifierModel
from tem.domain.history import (
    PredictionHistory,
    PredictionHistoryEntry,
    TransactionHistory,
)
from tem.domain.task import MLTask
from tem.domain.transaction import CreditTransaction
from tem.domain.user import Administrator, User


def main() -> None:
    admin = Administrator(email="admin@example.com", _password_hash="hashed-admin")
    user = User(email="user@example.com", _password_hash="hashed-user")
    print("Registered user:", user.email, "| balance:", user.balance)

    ledger = TransactionHistory()

    # Admin moderates a top-up request from the user.
    top_up = CreditTransaction(user, Decimal("10"))
    top_up.apply()
    ledger.add(top_up)
    print("After admin-approved top-up:", user.balance)

    model = KeywordEvidenceClassifierModel(
        model_id="evidence-mapper-keyword-v0",
        name="Keyword evidence classifier",
        description="Offline keyword baseline for evidence-to-category mapping",
        version="0.1",
        credit_cost=Decimal("1"),
    )

    items = [
        EvidenceItem(
            title="Open source observability library",
            description=(
                "I created and maintain an open source observability library used "
                "by many teams with measurable adoption"
            ),
            source_url="https://github.com/example/lib",
            metrics={"stars": 1200, "contributors": 23},
        ),
        EvidenceItem(title="", description="too short"),
        EvidenceItem(
            title="Conference keynote",
            description=(
                "I was invited to give a keynote about distributed systems at an "
                "international engineering conference"
            ),
        ),
    ]

    task = MLTask(user, model, items)
    result = task.execute()
    if task.debit_transaction is not None:
        ledger.add(task.debit_transaction)

    print()
    print("Task status:", task.status.value)
    print("Credits charged:", result.credits_charged)
    print("Balance after task:", user.balance)
    print("Invalid items:", [(error.item_index, error.messages) for error in result.invalid_items])
    for index, mapping in enumerate(result.predictions):
        print(
            f"  prediction {index}: primary={mapping.primary.category.value} "
            f"({mapping.primary.confidence}), review={mapping.human_review_required}"
        )

    history = PredictionHistory()
    history.add(
        PredictionHistoryEntry(task.id, user.id, model.version, tuple(items), result)
    )
    print()
    entry = history.for_user(user.id)[0]
    print("History entries for user:", len(history.for_user(user.id)))
    print("Uploaded items stored in history:", len(entry.items))

    # Админ проверяет каждую транзакцию
    print("Transactions visible to admin:", len(ledger.all()))
    for tx in ledger.all():
        print(f"  {tx.type.value} {tx.amount} by {tx.user.email} (task: {tx.task_id})")


if __name__ == "__main__":
    main()
