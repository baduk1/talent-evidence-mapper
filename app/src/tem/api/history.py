"""История ML-запросов и транзакций пользователя."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from .schemas import TaskHistoryEntry, TransactionEntry

history_route = APIRouter()


@history_route.get("/{user_id}/predictions", response_model=list[TaskHistoryEntry])
def prediction_history(
    user_id: str, session: Session = Depends(get_session)
) -> list[TaskHistoryEntry]:
    if crud.get_user_by_id(session, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return [
        TaskHistoryEntry(
            task_id=task.id,
            model_id=task.model_id,
            status=task.status.value,
            credits_charged=task.credits_charged,
            created_at=task.created_at,
        )
        for task in crud.list_tasks_for_user(session, user_id)
    ]


@history_route.get("/{user_id}/transactions", response_model=list[TransactionEntry])
def transaction_history(
    user_id: str, session: Session = Depends(get_session)
) -> list[TransactionEntry]:
    if crud.get_user_by_id(session, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return [
        TransactionEntry(
            id=tx.id,
            amount=tx.amount,
            type=tx.type.value,
            task_id=tx.task_id,
            created_at=tx.created_at,
        )
        for tx in crud.list_transactions_for_user(session, user_id)
    ]