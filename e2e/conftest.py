"""Фикстуры сквозных тестов против живого docker-compose стека.

Запуск (стек должен быть поднят: docker-compose up -d --scale ml_worker=2):

    pytest e2e/ -v

Тесты идут по-настоящему сквозным путём: HTTP -> nginx -> FastAPI ->
RabbitMQ -> воркер -> Postgres -> HTTP. Каждый тест независим: работает
под своим свежесозданным пользователем и сам выстраивает предусловия.
"""
import time
import uuid

import httpx
import pytest

BASE_URL = "http://localhost"  # nginx, порт 80
TIMEOUT = 30.0                 # сколько ждём обработки воркером


@pytest.fixture()
def client():
    """HTTP-клиент, ходящий на живой стек через nginx."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture()
def credentials():
    """Уникальный email на каждый тест — гарантия независимости."""
    return {"email": f"e2e-{uuid.uuid4().hex[:8]}@test.com", "password": "secret"}


@pytest.fixture()
def registered_user(client, credentials):
    """Пользователь, зарегистрированный в системе."""
    response = client.post("/api/auth/signup", json=credentials)
    assert response.status_code == 201
    return credentials


@pytest.fixture()
def auth_headers(client, registered_user):
    """Заголовок авторизации с живым токеном."""
    response = client.post("/api/auth/signin", json=registered_user)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def valid_item():
    """Фабрика валидных элементов батча (title можно переопределить)."""
    def make(title="Open source library"):
        return {
            "title": title,
            "description": (
                "I created and maintain an open source observability library "
                "with measurable impact and many users"
            ),
        }
    return make


@pytest.fixture()
def invalid_item():
    """Элемент, не проходящий валидацию."""
    return {"title": "", "description": "short"}


@pytest.fixture()
def top_up(client):
    """Пополняет баланс на указанную сумму, проверяя успешность операции."""
    def do_top_up(headers, amount):
        response = client.post(
            "/api/balance/topup", json={"amount": amount}, headers=headers
        )
        assert response.status_code == 200
    return do_top_up


@pytest.fixture()
def wait_task():
    """Опрашивает результат, пока воркер не закончит (иначе TimeoutError)."""
    def wait(client, headers, task_id):
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            body = client.get(f"/api/predict/{task_id}", headers=headers).json()
            if body["status"] != "created":
                return body
            time.sleep(1)
        raise TimeoutError(f"задача {task_id} не обработалась за {TIMEOUT} секунд")
    return wait
