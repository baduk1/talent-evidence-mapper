"""История ML-запросов и транзакций. Смотрим только свою - из токена."""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import UserORM
from .schemas import TaskHistoryEntry, TransactionEntry
from .security import get_current_user

history_route = APIRouter()


@history_route.get("/predictions", response_model=list[TaskHistoryEntry])
def prediction_history(
    user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[TaskHistoryEntry]:
    return [
        TaskHistoryEntry(
            task_id=task.id,
            model_id=task.model_id,
            status=task.status.value,
            credits_charged=task.credits_charged,
            created_at=task.created_at,
        )
        for task in crud.list_tasks_for_user(session, user.id)
    ]


@history_route.get("/transactions", response_model=list[TransactionEntry])
def transaction_history(
    user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[TransactionEntry]:
    return [
        TransactionEntry(
            id=tx.id,
            amount=tx.amount,
            type=tx.type.value,
            task_id=tx.task_id,
            created_at=tx.created_at,
        )
        for tx in crud.list_transactions_for_user(session, user.id)
    ]