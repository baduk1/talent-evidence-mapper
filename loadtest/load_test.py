"""Нагрузочный тест против живого стека.

Запуск (стек поднят: docker compose up -d --scale ml_worker=2):

    python loadtest/load_test.py --users 10 --tasks 3

Каждый виртуальный пользователь проходит честный путь: регистрация ->
вход -> пополнение -> N задач на предсказание -> ожидание результата.
Меряем латентность HTTP-шагов, RPS, время осадка очереди и долю ошибок.

За поведением системы во время прогона удобно следить в Grafana
(http://localhost:3000, admin/admin) и в админке RabbitMQ (:15672).
"""
import argparse
import asyncio
import statistics
import time
import uuid

import httpx

VALID_ITEM = {
    "title": "Open source library",
    "description": (
        "I created and maintain an open source observability library "
        "with measurable impact and many users"
    ),
}


class Stats:
    def __init__(self) -> None:
        self.latencies: list[float] = []
        self.errors: list[str] = []

    def record(self, started: float) -> None:
        self.latencies.append(time.perf_counter() - started)


async def timed(client: httpx.AsyncClient, method: str, url: str, stats: Stats, **kwargs):
    started = time.perf_counter()
    response = await client.request(method, url, **kwargs)
    stats.record(started)
    if response.status_code >= 500:
        stats.errors.append(f"{method} {url} -> {response.status_code}")
    return response


async def user_flow(client: httpx.AsyncClient, index: int, tasks: int, stats: Stats) -> None:
    """Полный путь одного пользователя, задачи ждём до финального статуса."""
    email = f"load-{uuid.uuid4().hex[:8]}@test.com"
    credentials = {"email": email, "password": "secret"}

    response = await timed(client, "POST", "/api/auth/signup", stats, json=credentials)
    if response.status_code != 201:
        stats.errors.append(f"signup {email} -> {response.status_code}")
        return

    response = await timed(client, "POST", "/api/auth/signin", stats, json=credentials)
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    await timed(client, "POST", "/api/balance/topup", stats, json={"amount": tasks + 1}, headers=headers)

    task_ids = []
    for i in range(tasks):
        item = dict(VALID_ITEM, title=f"Load item {index}-{i}")
        response = await timed(client, "POST", "/api/predict", stats, json={"items": [item]}, headers=headers)
        if response.status_code == 202:
            task_ids.append(response.json()["task_id"])

    # Ждём, пока воркеры обработают задачи этого пользователя.
    pending = set(task_ids)
    deadline = time.perf_counter() + 120
    while pending and time.perf_counter() < deadline:
        for task_id in list(pending):
            response = await timed(client, "GET", f"/api/predict/{task_id}", stats, headers=headers)
            if response.json()["status"] != "created":
                pending.discard(task_id)
        if pending:
            await asyncio.sleep(1)
    if pending:
        stats.errors.append(f"user {index}: {len(pending)} задач не обработаны за 120с")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=10, help="виртуальных пользователей")
    parser.add_argument("--tasks", type=int, default=3, help="ML-задач на пользователя")
    parser.add_argument("--base", default="http://localhost", help="базовый URL стека")
    args = parser.parse_args()

    stats = Stats()
    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=args.base, timeout=30.0) as client:
        await asyncio.gather(*[user_flow(client, i, args.tasks, stats) for i in range(args.users)])
    wall = time.perf_counter() - started

    lat = sorted(stats.latencies)
    total_requests = len(lat)
    predictions = args.users * args.tasks

    def percentile(p: float) -> float:
        return lat[min(int(len(lat) * p), len(lat) - 1)] if lat else 0.0

    print(f"\nВиртуальных пользователей: {args.users}, ML-задач: {predictions}")
    print(f"HTTP-запросов: {total_requests}, ошибок: {len(stats.errors)}")
    print(f"Общее время: {wall:.1f}с, RPS: {total_requests / wall:.1f}")
    if lat:
        print(f"Латентность: p50={percentile(0.5) * 1000:.0f}мс, "
              f"p95={percentile(0.95) * 1000:.0f}мс, "
              f"среднее={statistics.mean(lat) * 1000:.0f}мс")
    if stats.errors:
        print("Ошибки:")
        for error in stats.errors[:10]:
            print(f"  {error}")


if __name__ == "__main__":
    asyncio.run(main())
