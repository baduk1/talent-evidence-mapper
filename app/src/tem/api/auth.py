"""Регистрация и авторизация. После входа выдаём JWT."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import UserORM
from ..monitoring import SIGNUPS_TOTAL
from .schemas import SignInRequest, SignUpRequest, TokenResponse
from .security import create_access_token, get_current_user

auth_route = APIRouter()


def _hash_password(password: str) -> str:
    """Не храним пароль в открытом виде даже в учебном проекте."""
    return hashlib.sha256(password.encode()).hexdigest()


@auth_route.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(data: SignUpRequest, session: Session = Depends(get_session)) -> dict:
    if crud.get_user_by_email(session, data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )
    user = crud.create_user(session, data.email, _hash_password(data.password))
    session.commit()
    SIGNUPS_TOTAL.inc()
    return {"message": "Пользователь зарегистрирован", "user_id": user.id}


@auth_route.post("/signin", response_model=TokenResponse)
def signin(data: SignInRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = crud.get_user_by_email(session, data.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )
    if user.password_hash != _hash_password(data.password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный пароль",
        )
    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
    )


@auth_route.get("/me")
def me(user: UserORM = Depends(get_current_user)) -> dict:
    """Проверка токена: возвращает владельца токена."""
    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role.value,
        "balance": user.balance,
    }