"""Просмотр и пополнение баланса."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..domain.exceptions import InvalidAmountError
from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from .schemas import BalanceResponse, TopUpRequest

balance_route = APIRouter()


@balance_route.get("/{user_id}", response_model=BalanceResponse)
def get_balance(user_id: str, session: Session = Depends(get_session)) -> BalanceResponse:
    user = crud.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    return BalanceResponse(user_id=user.id, balance=user.balance)


@balance_route.post("/topup", response_model=BalanceResponse)
def top_up(data: TopUpRequest, session: Session = Depends(get_session)) -> BalanceResponse:
    # Эквайринг не подключаем по условию задания: кнопка "пополнить" просто
    # начисляет кредиты. Операция пишется в историю транзакций внутри crud.
    try:
        balance = crud.top_up(session, data.user_id, data.amount)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    except InvalidAmountError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    session.commit()
    return BalanceResponse(user_id=data.user_id, balance=balance)