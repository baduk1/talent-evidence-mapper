"""Сквозные тесты: история транзакций и ML-запросов."""


def test_transaction_history_shows_topup_and_charge(
    client, auth_headers, valid_item, top_up, wait_task
):
    top_up(auth_headers, 5)

    response = client.post(
        "/api/predict", json={"items": [valid_item()]}, headers=auth_headers
    )
    wait_task(client, auth_headers, response.json()["task_id"])

    transactions = client.get("/api/history/transactions", headers=auth_headers).json()
    types = [(tx["type"], tx["amount"]) for tx in transactions]
    assert ("credit", "5.00") in types
    assert ("debit", "1.00") in types


def test_prediction_history_shows_all_task_statuses(
    client, auth_headers, valid_item, invalid_item, top_up, wait_task
):
    top_up(auth_headers, 5)

    # Частично валидный батч -> partially_completed, списан 1 кредит
    response = client.post(
        "/api/predict",
        json={"items": [valid_item(), invalid_item]},
        headers=auth_headers,
    )
    first = wait_task(client, auth_headers, response.json()["task_id"])
    assert first["status"] == "partially_completed"

    # Пять валидных items при остатке 4 кредита -> failed
    items = [valid_item(title=f"Item {i}") for i in range(5)]
    response = client.post("/api/predict", json={"items": items}, headers=auth_headers)
    second = wait_task(client, auth_headers, response.json()["task_id"])
    assert second["status"] == "failed"

    tasks = client.get("/api/history/predictions", headers=auth_headers).json()
    assert len(tasks) == 2
    assert {t["status"] for t in tasks} == {"partially_completed", "failed"}
