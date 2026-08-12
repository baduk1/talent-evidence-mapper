"""Веб-интерфейс: страницы, cookie-авторизация, формы."""
import os

# До любых импортов tem: подменяем БД на in-memory.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from tem.infrastructure.db.database import get_session
from tem.infrastructure.db.seed import seed
from tem.main import app


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed(session)
        session.commit()
        yield session


@pytest.fixture()
def client(session):
    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def published(monkeypatch):
    """Перехватываем сообщения в RabbitMQ - в тестах брокера нет."""
    messages = []
    monkeypatch.setattr("tem.web.routes.send_task", messages.append)
    return messages


def signup_via_form(client, email="web@b.com", password="secret"):
    return client.post("/signup", data={"email": email, "password": password})


def test_home_page_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Talent Evidence Mapper" in response.text


def test_signup_via_form_lands_in_cabinet(client):
    response = signup_via_form(client)
    assert response.status_code == 200
    assert "Личный кабинет" in response.text
    assert "web@b.com" in response.text


def test_cabinet_requires_login(client):
    response = client.get("/cabinet", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_topup_via_form_updates_balance(client):
    signup_via_form(client)
    response = client.post("/topup", data={"amount": 10})
    assert "10" in response.text
    assert "Баланс пополнен" in response.text


def test_predict_via_form_publishes_message(client, published):
    signup_via_form(client)
    client.post("/topup", data={"amount": 10})
    response = client.post(
        "/predict",
        data={
            "title": "OSS library",
            "description": (
                "I created and maintain an open source library with measurable "
                "impact and many users"
            ),
            "source_url": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert len(published) == 1
    assert published[0]["items"][0]["title"] == "OSS library"


def test_history_page_shows_operations(client):
    signup_via_form(client)
    client.post("/topup", data={"amount": 10})
    response = client.get("/history")
    assert response.status_code == 200
    assert "пополнение" in response.text
