"""Отправка данных на предсказание - асинхронно, через RabbitMQ.
Личность пользователя берём из JWT, user_id в запросе не нужен."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import MLModelORM, UserORM
from ..infrastructure.mq import send_task
from .schemas import (
    PredictAccepted,
    PredictionRecordOut,
    PredictRequest,
    TaskResultResponse,
)
from .security import get_current_user

predict_route = APIRouter()


@predict_route.post("", response_model=PredictAccepted, status_code=status.HTTP_202_ACCEPTED)
def predict(
    data: PredictRequest,
    user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PredictAccepted:
    """Принять ML-задачу: строка в БД + сообщение в очередь. Обработку
    выполнят воркеры, результат смотрим через GET /api/predict/{task_id}."""
    if data.model_id is not None:
        model_orm = session.get(MLModelORM, data.model_id)
    else:
        model_orm = next(iter(crud.list_active_models(session)), None)
    if model_orm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Модель не найдена")

    task = crud.create_task(session, user.id, model_orm.id)
    session.commit()

    send_task(
        {
            "task_id": task.id,
            "user_id": user.id,
            "model_id": model_orm.id,
            "items": [item.model_dump() for item in data.items],
        }
    )
    return PredictAccepted(task_id=task.id, status="queued")


@predict_route.get("/{task_id}", response_model=TaskResultResponse)
def get_task_result(
    task_id: str,
    user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TaskResultResponse:
    """Статус задачи и результаты, когда воркер закончил. Только свои."""
    task = crud.get_task(session, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return TaskResultResponse(
        task_id=task.id,
        status=task.status.value,
        credits_charged=task.credits_charged,
        records=[
            PredictionRecordOut(
                item_index=record.item_index,
                title=record.title,
                primary_category=record.primary_category,
                confidence=record.confidence,
                human_review_required=record.human_review_required,
                worker_id=record.worker_id,
            )
            for record in crud.list_records_for_task(session, task_id)
        ],
    )