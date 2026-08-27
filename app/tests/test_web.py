"""Веб-интерфейс: страницы, cookie-авторизация, формы."""
import pytest


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
