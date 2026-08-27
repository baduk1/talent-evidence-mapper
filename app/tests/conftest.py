"""Общие фикстуры тестов: изолированная in-memory БД и HTTP-клиент."""
import os

# До любых импортов tem: подменяем БД на in-memory, чтобы startup-хук
# не трогал ни файл, ни Postgres.
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
    """Чистая in-memory БД с демо-данными; у каждого теста своя."""
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
    """TestClient с зависимостью get_session, подменённой на тестовую БД."""
    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
