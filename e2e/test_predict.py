"""Сквозные тесты: отправка данных на предсказание и получение результата."""


def test_partial_batch_processed_and_charged(
    client, auth_headers, valid_item, invalid_item, top_up, wait_task
):
    """Батч из валидного и невалидного item: валидные данные обработаны,
    ошибочные возвращены с причиной, кредит списан только за валидный."""
    top_up(auth_headers, 5)

    response = client.post(
        "/api/predict",
        json={"items": [valid_item(), invalid_item]},
        headers=auth_headers,
    )
    assert response.status_code == 202

    task = wait_task(client, auth_headers, response.json()["task_id"])
    assert task["status"] == "partially_completed"
    assert len(task["records"]) == 1
    assert len(task["invalid_items"]) == 1
    assert task["invalid_items"][0]["messages"]
    assert task["credits_charged"] == "1.00"

    balance = client.get("/api/balance", headers=auth_headers).json()["balance"]
    assert balance == "4.00"


def test_task_fails_when_balance_is_insufficient(
    client, auth_headers, valid_item, top_up, wait_task
):
    """При недостатке средств задача уходит в failed, списания нет."""
    top_up(auth_headers, 4)

    items = [valid_item(title=f"Item {i}") for i in range(5)]
    response = client.post("/api/predict", json={"items": items}, headers=auth_headers)
    assert response.status_code == 202

    task = wait_task(client, auth_headers, response.json()["task_id"])
    assert task["status"] == "failed"

    balance = client.get("/api/balance", headers=auth_headers).json()["balance"]
    assert balance == "4.00"
