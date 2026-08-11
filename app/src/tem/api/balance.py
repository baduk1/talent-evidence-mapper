"""Просмотр и пополнение баланса. Чей баланс - знаем из токена."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..domain.exceptions import InvalidAmountError
from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import UserORM
from .schemas import BalanceResponse, TopUpRequest
from .security import get_current_user

balance_route = APIRouter()


@balance_route.get("", response_model=BalanceResponse)
def get_balance(user: UserORM = Depends(get_current_user)) -> BalanceResponse:
    return BalanceResponse(user_id=user.id, balance=user.balance)


@balance_route.post("/topup", response_model=BalanceResponse)
def top_up(
    data: TopUpRequest,
    user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BalanceResponse:
    # Эквайринг не подключаем по условию задания: кнопка "пополнить" просто
    # начисляет кредиты. Операция пишется в историю транзакций внутри crud.
    try:
        balance = crud.top_up(session, user.id, data.amount)
    except InvalidAmountError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    session.commit()
    return BalanceResponse(user_id=user.id, balance=balance)