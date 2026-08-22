"""Сквозные тесты: баланс и его пополнение."""


def test_initial_balance_is_zero(client, auth_headers):
    body = client.get("/api/balance", headers=auth_headers).json()
    assert body["balance"] == "0.00"


def test_topup_updates_balance(client, auth_headers, top_up):
    top_up(auth_headers, 5)
    body = client.get("/api/balance", headers=auth_headers).json()
    assert body["balance"] == "5.00"


def test_negative_topup_rejected(client, auth_headers):
    response = client.post(
        "/api/balance/topup", json={"amount": -1}, headers=auth_headers
    )
    assert response.status_code == 400
