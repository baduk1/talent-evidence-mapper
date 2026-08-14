"""HTML-страницы личного кабинета.

Это тонкий слой поверх той же бизнес-логики, что и REST API: формы рендерятся
Jinja2, авторизация через JWT в HttpOnly-cookie. Бизнес-правила не дублируются:
деньги через crud, задачи уходят в RabbitMQ через send_task, обрабатывают воркеры.
"""
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ..api.security import create_access_token, get_user_by_token
from ..domain.exceptions import InvalidAmountError
from ..infrastructure.db import crud
from ..infrastructure.db.database import get_session
from ..infrastructure.db.models import UserORM
from ..infrastructure.mq import send_task

web_route = APIRouter(include_in_schema=False)  # страницы не светим в Swagger

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

COOKIE_NAME = "tem_token"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def _user_from_cookie(request: Request, session: Session) -> UserORM | None:
    token = request.cookies.get(COOKIE_NAME)
    return get_user_by_token(session, token) if token else None


@web_route.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    """Главная страница с описанием сервиса. Доступна без авторизации."""
    return templates.TemplateResponse(
        request, "index.html", {"user": _user_from_cookie(request, session)}
    )


@web_route.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse(request, "signup.html", {"user": None})


@web_route.post("/signup")
def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    if crud.get_user_by_email(session, email):
        return templates.TemplateResponse(
            request, "signup.html", {"user": None, "error": "email_taken"}
        )
    import hashlib

    user = crud.create_user(session, email, hashlib.sha256(password.encode()).hexdigest())
    session.commit()
    response = _redirect("/cabinet?msg=registered")
    response.set_cookie(COOKIE_NAME, create_access_token(user.id), httponly=True)
    return response


@web_route.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": None})


@web_route.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    import hashlib

    user = crud.get_user_by_email(session, email)
    if user is None or user.password_hash != hashlib.sha256(password.encode()).hexdigest():
        return templates.TemplateResponse(
            request, "login.html", {"user": None, "error": "wrong_credentials"}
        )
    response = _redirect("/cabinet")
    response.set_cookie(COOKIE_NAME, create_access_token(user.id), httponly=True)
    return response


@web_route.post("/logout")
def logout():
    response = _redirect("/")
    response.delete_cookie(COOKIE_NAME)
    return response


@web_route.get("/cabinet", response_class=HTMLResponse)
def cabinet(
    request: Request,
    msg: str = "",
    error: str = "",
    session: Session = Depends(get_session),
):
    user = _user_from_cookie(request, session)
    if user is None:
        return _redirect("/login")
    return templates.TemplateResponse(
        request, "cabinet.html", {"user": user, "msg": msg, "error": error}
    )


@web_route.post("/topup")
def topup(
    request: Request,
    amount: Decimal = Form(...),
    session: Session = Depends(get_session),
):
    user = _user_from_cookie(request, session)
    if user is None:
        return _redirect("/login")
    try:
        crud.top_up(session, user.id, amount)
    except InvalidAmountError:
        return _redirect("/cabinet?error=invalid_amount")
    session.commit()
    return _redirect("/cabinet?msg=topup_ok")


@web_route.post("/predict")
def predict(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    source_url: str = Form(""),
    session: Session = Depends(get_session),
):
    """Форма отправляет одно доказательство. Задача уходит воркерам через
    очередь - как и из REST API, валидация и списание на их стороне."""
    user = _user_from_cookie(request, session)
    if user is None:
        return _redirect("/login")
    model_orm = next(iter(crud.list_active_models(session)), None)
    if model_orm is None:
        return _redirect("/cabinet?error=no_model")
    task = crud.create_task(session, user.id, model_orm.id)
    session.commit()
    send_task(
        {
            "task_id": task.id,
            "user_id": user.id,
            "model_id": model_orm.id,
            "items": [
                {
                    "title": title,
                    "description": description,
                    "evidence_type": None,
                    "source_url": source_url or None,
                    "metrics": {},
                }
            ],
        }
    )
    return _redirect(f"/tasks/{task.id}?msg=queued")


@web_route.get("/history", response_class=HTMLResponse)
def history(request: Request, session: Session = Depends(get_session)):
    user = _user_from_cookie(request, session)
    if user is None:
        return _redirect("/login")
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "user": user,
            "tasks": crud.list_tasks_for_user(session, user.id),
            "transactions": crud.list_transactions_for_user(session, user.id),
        },
    )


@web_route.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(
    task_id: str,
    request: Request,
    msg: str = "",
    session: Session = Depends(get_session),
):
    """Страница задачи: статус, списание, обработанные и отклонённые items."""
    user = _user_from_cookie(request, session)
    if user is None:
        return _redirect("/login")
    task = crud.get_task(session, task_id)
    if task is None or task.user_id != user.id:
        return _redirect("/history")
    return templates.TemplateResponse(
        request,
        "task.html",
        {
            "user": user,
            "task": task,
            "msg": msg,
            "records": crud.list_records_for_task(session, task.id),
            "item_errors": crud.list_item_errors_for_task(session, task.id),
        },
    )