import os

# До любых импортов tem: подменяем БД на in-memory, чтобы startup-хук
# не трогал ни файл, ни Postgres.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from tem.infrastructure.db import crud
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
    monkeypatch.setattr("tem.api.predict.send_task", messages.append)
    return messages


def signup(client, email="api@b.com", password="secret") -> str:
    response = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()["user_id"]


def auth_headers(client, email="api@b.com", password="secret") -> dict:
    """signup + signin, возвращает заголовок с живым токеном."""
    signup(client, email, password)
    response = client.post("/api/auth/signin", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def valid_item(title="OSS library") -> dict:
    return {
        "title": title,
        "description": (
            "I created and maintain an open source library with measurable impact "
            "and many users"
        ),
    }


def test_signup_and_signin_returns_token(client):
    signup(client)
    response = client.post("/api/auth/signin", json={"email": "api@b.com", "password": "secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_signup_duplicate_email_conflict(client):
    signup(client)
    response = client.post("/api/auth/signup", json={"email": "api@b.com", "password": "x"})
    assert response.status_code == 409


def test_signin_wrong_password(client):
    signup(client)
    response = client.post("/api/auth/signin", json={"email": "api@b.com", "password": "no"})
    assert response.status_code == 403


def test_me_with_and_without_token(client):
    headers = auth_headers(client)
    assert client.get("/api/auth/me", headers=headers).json()["email"] == "api@b.com"
    assert client.get("/api/auth/me").status_code == 403


def test_garbage_token_rejected(client):
    headers = {"Authorization": "Bearer garbage"}
    assert client.get("/api/balance", headers=headers).status_code == 401


def test_balance_topup_flow(client):
    headers = auth_headers(client)
    assert client.get("/api/balance", headers=headers).json()["balance"] == "0.00"
    response = client.post("/api/balance/topup", json={"amount": 10}, headers=headers)
    assert response.status_code == 200
    assert response.json()["balance"] == "10.00"


def test_balance_requires_token(client):
    assert client.get("/api/balance").status_code == 403


def test_topup_rejects_non_positive_amount(client):
    headers = auth_headers(client)
    response = client.post("/api/balance/topup", json={"amount": 0}, headers=headers)
    assert response.status_code == 400


def test_predict_queues_task_and_publishes_message(client, published):
    headers = auth_headers(client)
    response = client.post(
        "/api/predict",
        json={"items": [valid_item()]},
        headers=headers,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"

    # Сообщение ушло в очередь ровно с этой задачей
    assert len(published) == 1
    assert published[0]["task_id"] == body["task_id"]
    assert published[0]["items"][0]["title"] == "OSS library"

    # Задача лежит в БД со статусом created, результатов пока нет
    result = client.get(f"/api/predict/{body['task_id']}", headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "created"
    assert result.json()["records"] == []


def test_predict_requires_token(client, published):
    response = client.post("/api/predict", json={"items": [valid_item()]})
    assert response.status_code == 403
    assert published == []


def test_get_task_result_only_own(client, published):
    headers = auth_headers(client)
    task_id = client.post(
        "/api/predict", json={"items": [valid_item()]}, headers=headers
    ).json()["task_id"]

    # Чужая задача для другого пользователя выглядит как несуществующая
    other_headers = auth_headers(client, email="other@b.com")
    assert client.get(f"/api/predict/{task_id}", headers=other_headers).status_code == 404


def test_history_endpoints_show_only_own_data(client, published):
    headers = auth_headers(client)
    client.post("/api/balance/topup", json={"amount": 5}, headers=headers)
    client.post("/api/predict", json={"items": [valid_item()]}, headers=headers)

    transactions = client.get("/api/history/transactions", headers=headers).json()
    assert [tx["type"] for tx in transactions] == ["credit"]

    predictions = client.get("/api/history/predictions", headers=headers).json()
    assert len(predictions) == 1
    assert predictions[0]["status"] == "created"

    # Другой пользователь не видит чужую историю
    other_headers = auth_headers(client, email="other@b.com")
    assert client.get("/api/history/predictions", headers=other_headers).json() == []
    assert client.get("/api/history/transactions", headers=other_headers).json() == []