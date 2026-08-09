"""Отправка данных на предсказание."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..domain.enums import TaskStatus
from ..domain.evidence import EvidenceItem, KeywordEvidenceClassifierModel
from ..domain.exceptions import InsufficientBalanceError
from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import MLModelORM
from .schemas import (
    CategoryScoreOut,
    InvalidItemOut,
    PredictRequest,
    PredictResponse,
    PredictionOut,
)

predict_route = APIRouter()


def _score_out(score) -> CategoryScoreOut:
    return CategoryScoreOut(category=score.category.value, confidence=score.confidence)


def _prediction_out(item: EvidenceItem, model: KeywordEvidenceClassifierModel) -> PredictionOut:
    mapping = model.predict(item)
    return PredictionOut(
        title=item.title,
        primary=_score_out(mapping.primary),
        secondary=[_score_out(score) for score in mapping.secondary],
        missing_information=list(mapping.missing_information),
        human_review_required=mapping.human_review_required,
    )


@predict_route.post("", response_model=PredictResponse)
def predict(data: PredictRequest, session: Session = Depends(get_session)) -> PredictResponse:
    user = crud.get_user_by_id(session, data.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    if data.model_id is not None:
        model_orm = session.get(MLModelORM, data.model_id)
    else:
        model_orm = next(iter(crud.list_active_models(session)), None)
    if model_orm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Модель не найдена")

    # Доменная модель считает валидацию и предсказание - правила не дублируем.
    model = KeywordEvidenceClassifierModel(
        model_id=model_orm.id,
        name=model_orm.name,
        description="",
        version=model_orm.version,
        credit_cost=model_orm.credit_cost,
    )

    valid: list[EvidenceItem] = []
    invalid: list[InvalidItemOut] = []
    for index, item_in in enumerate(data.items):
        item = EvidenceItem(**item_in.model_dump())
        messages = model.validate_input(item)
        if messages:
            invalid.append(InvalidItemOut(item_index=index, messages=messages))
        else:
            valid.append(item)

    task = crud.create_task(session, user.id, model_orm.id)

    # Списываем только за валидные items. Не хватило средств - задача FAILED,
    # ничего не списано.
    cost = model_orm.credit_cost * len(valid)
    try:
        if cost > 0:
            crud.charge(session, user.id, cost, task_id=task.id)
    except InsufficientBalanceError:
        crud.finish_task(session, task.id, TaskStatus.FAILED, Decimal("0"))
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Недостаточно средств на балансе",
        )

    predictions = [_prediction_out(item, model) for item in valid]
    task_status = TaskStatus.COMPLETED if not invalid else TaskStatus.PARTIALLY_COMPLETED
    crud.finish_task(session, task.id, task_status, cost)
    session.commit()

    return PredictResponse(
        task_id=task.id,
        status=task_status.value,
        predictions=predictions,
        invalid_items=invalid,
        credits_charged=cost,
        balance=crud.get_user_by_id(session, user.id).balance,
    )