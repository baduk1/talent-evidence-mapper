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


def signup(client, email="api@b.com", password="secret") -> str:
    response = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()["user_id"]


def valid_item(title="OSS library") -> dict:
    return {
        "title": title,
        "description": (
            "I created and maintain an open source library with measurable impact "
            "and many users"
        ),
    }


def test_signup_and_signin(client):
    user_id = signup(client)
    response = client.post("/api/auth/signin", json={"email": "api@b.com", "password": "secret"})
    assert response.status_code == 200
    assert response.json()["user_id"] == user_id


def test_signup_duplicate_email_conflict(client):
    signup(client)
    response = client.post("/api/auth/signup", json={"email": "api@b.com", "password": "x"})
    assert response.status_code == 409


def test_signin_wrong_password(client):
    signup(client)
    response = client.post("/api/auth/signin", json={"email": "api@b.com", "password": "no"})
    assert response.status_code == 403


def test_balance_topup_flow(client):
    user_id = signup(client)
    assert client.get(f"/api/balance/{user_id}").json()["balance"] == "0.00"
    response = client.post("/api/balance/topup", json={"user_id": user_id, "amount": 10})
    assert response.status_code == 200
    assert response.json()["balance"] == "10.00"


def test_topup_unknown_user(client):
    response = client.post("/api/balance/topup", json={"user_id": "nope", "amount": 10})
    assert response.status_code == 404


def test_topup_rejects_non_positive_amount(client):
    user_id = signup(client)
    response = client.post("/api/balance/topup", json={"user_id": user_id, "amount": 0})
    assert response.status_code == 400


def test_predict_charges_only_valid_items(client):
    user_id = signup(client)
    client.post("/api/balance/topup", json={"user_id": user_id, "amount": 10})
    response = client.post(
        "/api/predict",
        json={"user_id": user_id, "items": [valid_item(), {"title": "", "description": "short"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partially_completed"
    assert body["credits_charged"] == "1.00"
    assert body["balance"] == "9.00"
    assert len(body["predictions"]) == 1
    assert body["invalid_items"][0]["item_index"] == 1


def test_predict_insufficient_balance(client):
    user_id = signup(client)
    client.post("/api/balance/topup", json={"user_id": user_id, "amount": 1})
    response = client.post(
        "/api/predict",
        json={"user_id": user_id, "items": [valid_item("One"), valid_item("Two")]},
    )
    assert response.status_code == 402
    assert client.get(f"/api/balance/{user_id}").json()["balance"] == "1.00"


def test_history_endpoints(client):
    user_id = signup(client)
    client.post("/api/balance/topup", json={"user_id": user_id, "amount": 5})
    client.post("/api/predict", json={"user_id": user_id, "items": [valid_item()]})

    transactions = client.get(f"/api/history/{user_id}/transactions").json()
    assert [tx["type"] for tx in transactions] == ["debit", "credit"]

    predictions = client.get(f"/api/history/{user_id}/predictions").json()
    assert len(predictions) == 1
    assert predictions[0]["status"] == "completed"
    assert predictions[0]["credits_charged"] == "1.00"