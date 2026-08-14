"""JWT: выпуск и проверка токенов, зависимость "текущий пользователь".

После входа клиент получает токен и передаёт его в заголовке
Authorization: Bearer <token>. Эндпоинты больше не принимают user_id -
личность берём из токена, чужие данные так не посмотреть.
Веб-интерфейс использует тот же токен, но из HttpOnly-cookie.
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from ..infrastructure.db import crud
from ..infrastructure.db.config import get_settings
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import UserORM

bearer = HTTPBearer()


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_user_by_token(session: Session, token: str) -> UserORM | None:
    """Общая проверка токена: и для Bearer-заголовка, и для cookie."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    return crud.get_user_by_id(session, payload["sub"])


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    session: Session = Depends(get_session),
) -> UserORM:
    """Зависимость FastAPI: достаёт пользователя из Bearer-токена."""
    user = get_user_by_token(session, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный токен",
        )
    return user