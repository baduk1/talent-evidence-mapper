"""Сквозные тесты: живость сервиса, регистрация и авторизация."""


def test_service_is_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_signup_creates_user(client, credentials):
    response = client.post("/api/auth/signup", json=credentials)
    assert response.status_code == 201


def test_signup_duplicate_email_rejected(client, registered_user):
    response = client.post("/api/auth/signup", json=registered_user)
    assert response.status_code == 409


def test_signin_wrong_password_rejected(client, registered_user):
    response = client.post(
        "/api/auth/signin",
        json={"email": registered_user["email"], "password": "wrong"},
    )
    assert response.status_code == 403


def test_signin_returns_token(client, registered_user):
    response = client.post("/api/auth/signin", json=registered_user)
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_relogin_both_tokens_valid(client, registered_user):
    first = client.post("/api/auth/signin", json=registered_user)
    second = client.post("/api/auth/signin", json=registered_user)
    for token in (first.json()["access_token"], second.json()["access_token"]):
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200
