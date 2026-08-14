
"""Сквозная проверка системы против живого docker-compose стека.

Запуск (стек должен быть поднят: docker-compose up -d --scale ml_worker=2):

    python e2e/e2e_check.py

Идём по обязательным сценариям задания 7 по-настоящему сквозным путём:
HTTP -> nginx -> FastAPI -> RabbitMQ -> воркер -> Postgres -> HTTP.
Каждый сценарий печатает PASS/FAIL, в конце сводка; выход ненулевой, если
что-то упало.
"""
import sys
import time
import uuid

import httpx

BASE_URL = "http://localhost"  # nginx, порт 80
TIMEOUT = 30.0                 # сколько ждём обработки воркером

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def wait_task(client: httpx.Client, headers: dict, task_id: str) -> dict:
    """Опрашиваем результат, пока воркер не закончит."""
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        body = client.get(f"/api/predict/{task_id}", headers=headers).json()
        if body["status"] != "created":
            return body
        time.sleep(1)
    raise TimeoutError(f"задача {task_id} не обработалась за {TIMEOUT} секунд")


def main() -> int:
    email = f"e2e-{uuid.uuid4().hex[:8]}@test.com"
    password = "secret"
    valid_item = {
        "title": "Open source library",
        "description": (
            "I created and maintain an open source observability library "
            "with measurable impact and many users"
        ),
    }
    invalid_item = {"title": "", "description": "short"}

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # --- 0. Стек жив ---
        check("сервис отвечает на /health",
              client.get("/health").json() == {"status": "healthy"})

        # --- 1. Пользователи ---
        response = client.post("/api/auth/signup", json={"email": email, "password": password})
        check("создание пользователя", response.status_code == 201)

        response = client.post("/api/auth/signup", json={"email": email, "password": password})
        check("дубль email отклоняется", response.status_code == 409)

        response = client.post("/api/auth/signin", json={"email": email, "password": "wrong"})
        check("неверный пароль отклоняется", response.status_code == 403)

        response = client.post("/api/auth/signin", json={"email": email, "password": password})
        token = response.json().get("access_token", "")
        check("авторизация выдаёт токен", response.status_code == 200 and bool(token))
        headers = {"Authorization": f"Bearer {token}"}

        # повторная авторизация: второй токен тоже работает
        response = client.post("/api/auth/signin", json={"email": email, "password": password})
        headers2 = {"Authorization": f"Bearer {response.json()['access_token']}"}
        check("повторная авторизация, оба токена валидны",
              client.get("/api/auth/me", headers=headers2).status_code == 200)

        # --- 2. Баланс ---
        balance = client.get("/api/balance", headers=headers).json()["balance"]
        check("начальный баланс нулевой", balance == "0.00")

        response = client.post("/api/balance/topup", json={"amount": 5}, headers=headers)
        check("пополнение баланса", response.status_code == 200)
        balance = client.get("/api/balance", headers=headers).json()["balance"]
        check("баланс обновился после пополнения", balance == "5.00")

        response = client.post("/api/balance/topup", json={"amount": -1}, headers=headers)
        check("пополнение на отрицательную сумму отклоняется", response.status_code == 400)

        # --- 3 + 4. ML-запрос: частично валидный батч ---
        response = client.post(
            "/api/predict", json={"items": [valid_item, invalid_item]}, headers=headers
        )
        check("запрос принят в обработку", response.status_code == 202)
        task_id = response.json()["task_id"]

        task = wait_task(client, headers, task_id)
        check("воркер обработал задачу", task["status"] == "partially_completed", task["status"])
        check("валидные данные обработаны", len(task["records"]) == 1)
        check("ошибочные данные возвращены с причиной",
              len(task["invalid_items"]) == 1
              and bool(task["invalid_items"][0]["messages"]))
        check("списан 1 кредит только за валидный item",
              task["credits_charged"] == "1.00", task["credits_charged"])
        balance = client.get("/api/balance", headers=headers).json()["balance"]
        check("баланс после предсказания", balance == "4.00", balance)

        # --- 3. Запрет списания при недостаточном балансе ---
        response = client.post(
            "/api/predict",
            json={"items": [dict(valid_item, title=f"Item {i}") for i in range(5)]},
            headers=headers,
        )
        task = wait_task(client, headers, response.json()["task_id"])
        check("задача без средств уходит в failed", task["status"] == "failed", task["status"])
        balance = client.get("/api/balance", headers=headers).json()["balance"]
        check("при failed ничего не списано", balance == "4.00", balance)

        # --- 5. История ---
        txs = client.get("/api/history/transactions", headers=headers).json()
        types = [(tx["type"], tx["amount"]) for tx in txs]
        check("история транзакций: пополнение и списание",
              ("credit", "5.00") in types and ("debit", "1.00") in types, str(types))

        tasks = client.get("/api/history/predictions", headers=headers).json()
        check("история ML-запросов: обе задачи со статусами",
              len(tasks) == 2 and {t["status"] for t in tasks} == {"partially_completed", "failed"})

    failed = [name for name, ok, _ in results if not ok]
    print(f"\nИтого: {len(results) - len(failed)}/{len(results)} сценариев прошло")
    if failed:
        print("Упали: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())