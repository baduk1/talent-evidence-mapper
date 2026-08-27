# Talent Evidence Mapper

ML-сервис с личным кабинетом. Пользователь регистрируется, пополняет баланс,
отправляет пакет доказательств (описаний профессиональных достижений) и получает
маппинг каждого доказательства в категорию кандидата. Кредиты списываются
только за успешно обработанные элементы; ошибочные возвращаются с причинами
отклонения.

Задача ML: multilingual zero-shot классификация текстов достижений.
Боевой движок воркера — [`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli)
(MNLI + XNLI, 15 языков включая русский, лицензия MIT): текст становится
посылкой, описание категории — гипотезой, скор категории — вероятностью
entailment. Офлайн-модель на ключевых словах остаётся запасным движком:
она обслуживает юнит-тесты и демо без ML-зависимостей.

Финальный проект курса «Практикум по разработке ML сервисов на Python».

## Функционал

- Регистрация и авторизация: JWT (Bearer-токен для REST API,
  HttpOnly-cookie для веб-интерфейса), повторный вход, защита чужих данных
- Баланс: просмотр и пополнение; списание строго за валидные данные,
  запрет списания при недостатке средств
- ML-предсказание: пакетная отправка доказательств, постановка задачи
  в очередь RabbitMQ, асинхронная обработка воркерами
- Частично валидные батчи: валидные элементы обрабатываются, ошибочные
  сохраняются с причинами отклонения (статус `partially_completed`)
- История: транзакции и ML-запросы пользователя (REST API и веб-страницы)
- Веб-интерфейс личного кабинета поверх той же бизнес-логики, что и API,
  на двух языках (RU/EN)
- Telegram-бот (aiogram, asyncio): третий интерфейс с тем же функционалом,
  выбор языка на старте
- Админ-панель: пополнение баланса любого пользователя и просмотр всех
  транзакций (роль admin)
- Мониторинг: метрики Prometheus (/metrics, бизнес-счётчики, очереди
  RabbitMQ) и дашборд Grafana; нагрузочный тест в loadtest/

## Архитектура

```
                 ┌────────────┐      ┌──────────────┐
 HTTP клиент ──► │  nginx     │ ───► │  FastAPI app │ ───► PostgreSQL
                 │ (web-proxy)│      │ REST + Jinja2│
                 └────────────┘      └──────┬───────┘
                                            │ publish
 Telegram ────►  bot (aiogram) ────────────►│
                                            ▼
                                     ┌─────────────┐      ┌──────────────┐
                                     │  RabbitMQ   │ ───► │  ml_worker   │ ───► PostgreSQL
                                     │   очередь   │      │ (×N реплик)  │
                                     └─────────────┘      └──────────────┘
        app /metrics ──► Prometheus ──► Grafana        RabbitMQ :15692 ──► Prometheus
```

Сервисы docker-compose: `web-proxy` (nginx), `app` (FastAPI: REST + веб),
`database` (PostgreSQL 16), `rabbitmq` (брокер + админка + метрики),
`ml_worker` (обработчик задач, масштабируется), `bot` (Telegram),
`prometheus` и `grafana` (мониторинг).

Стек: FastAPI, SQLModel, PostgreSQL, RabbitMQ, nginx, Jinja2, aiogram 3,
transformers + PyTorch (CPU) в воркере, Prometheus + Grafana,
Docker Compose, pytest, httpx.

## Запуск

Требования: Docker с docker compose.

```bash
docker compose up -d --build
# опционально: несколько воркеров
docker compose up -d --scale ml_worker=2
```

Первая сборка воркера скачивает веса mDeBERTa (~1 ГБ) и занимает несколько
минут; дальше они закэшированы в образе, и стек работает без интернета.

После старта:

- Веб-интерфейс: http://localhost/ (регистрация → личный кабинет)
- Swagger UI: http://localhost/api/docs
- Healthcheck: http://localhost/health
- Админка RabbitMQ: http://localhost:15672 (guest/guest)
- Grafana: http://localhost:3000 (admin/admin, дашборд провижинится сам)
- Prometheus: http://localhost:9090
- Админ-панель: http://localhost/admin (демо-доступ admin@example.com / admin123)
- Telegram-бот: @talent_evidence_mapper_bot (нужен TELEGRAM_BOT_TOKEN
  в app/.env, берётся у @BotFather)

База создаётся и наполняется демо-моделями автоматически при старте
(seed идемпотентный). Данные переживают перезапуск (volume'ы в ./data).

Остановка:

```bash
docker compose down        # остановить
docker compose down -v     # остановить и удалить данные
```

Если после перезагрузки машины `curl http://localhost/health` отвечает
502 — пересоздайте контейнеры (`docker compose down && docker compose up -d`):
данные на bind-mount'ах переживут пересоздание, а битый lock-файл сокета
Postgres, оставшийся в слое остановленного контейнера, исчезнет. Устаревший
IP апстрима в nginx дополнительно исключён конфигом (resolver + переменная
в proxy_pass переразрешают имя app каждые 10 секунд).

## Использование

### Веб-интерфейс

`/` → `/signup` (регистрация, сразу вход по cookie) → `/cabinet`
(баланс, пополнение, форма отправки доказательства) → `/tasks/{id}`
(статус задачи, результаты, причины отклонения) → `/history`
(все операции: пополнения, списания, задачи со статусами).

### REST API

```bash
# регистрация и авторизация
curl -X POST http://localhost/api/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email": "demo@test.com", "password": "secret"}'

TOKEN=$(curl -s -X POST http://localhost/api/auth/signin \
  -H 'Content-Type: application/json' \
  -d '{"email": "demo@test.com", "password": "secret"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# пополнение баланса
curl -X POST http://localhost/api/balance/topup \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"amount": 5}'

# отправка пакета на предсказание (202 + task_id)
curl -X POST http://localhost/api/predict \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"items": [{"title": "Open source library",
       "description": "I created and maintain an open source observability library with measurable impact and many users"}]}'

# результат задачи (статус, записи, отклонённые items, списание)
curl http://localhost/api/predict/<task_id> -H "Authorization: Bearer $TOKEN"

# история
curl http://localhost/api/history/predictions  -H "Authorization: Bearer $TOKEN"
curl http://localhost/api/history/transactions -H "Authorization: Bearer $TOKEN"
```

## Telegram-бот

`@talent_evidence_mapper_bot` на aiogram 3 (asyncio, long polling). Аккаунт
привязывается к telegram id: регистрация и авторизация происходят сами
при выборе языка на первом экране. Команды:

- `/balance` - баланс кредитов
- `/topup 10` - пополнение баланса
- `/predict` - диалог: название, описание; результат приходит отдельным
  сообщением после обработки воркером
- `/history` - последние задачи и транзакции
- `/lang` - сменить язык (RU/EN)

## Администрирование (бонусный пункт)

Роль admin: пополнение баланса любого пользователя (модерация пополнений)
и просмотр всех транзакций системы. Демо-доступ: admin@example.com /
admin123, панель на `/admin`, журнал на `/admin/transactions`.

## Мониторинг и нагрузочное тестирование

Три уровня метрик: технические HTTP (RPS, латентность, коды - через
prometheus-fastapi-instrumentator на `/metrics`), очереди RabbitMQ
(плагин rabbitmq_prometheus на :15692) и бизнес-события
(`tem_signups_total`, `tem_topups_total`, `tem_predictions_total`).
Prometheus собирает всё в `monitoring/prometheus.yml`, дашборд Grafana
провижинится из `monitoring/grafana/provisioning`.

Нагрузочный тест (стек должен быть поднят):

```bash
python loadtest/load_test.py --users 10 --tasks 3
```

Виртуальные пользователи проходят полный путь (регистрация -> вход ->
пополнение -> задачи -> ожидание результата), скрипт печатает RPS,
латентность p50/p95 и ошибки. Эталонный прогон: 10 пользователей x 3
задачи, 0 ошибок, p95 < 50 мс на HTTP-шаг.

## Тестирование

```bash
cd app && pytest -q     # 58 юнит/интеграционных тестов (sqlite in-memory)
pytest e2e/ -v          # 13 сквозных тестов против живого стека
                        # (нужен поднятый docker compose)
```

Общие фикстуры — в `app/tests/conftest.py` и `e2e/conftest.py`; каждый
тест независим (своя БД / свой пользователь). Подробности покрытия —
в [TESTING.md](TESTING.md).

## Структура проекта

```
├── app/                        # FastAPI-приложение
│   ├── src/tem/
│   │   ├── domain/             # объектная модель (задание 1)
│   │   ├── infrastructure/db/  # ORM, CRUD, seed (задание 3)
│   │   ├── infrastructure/mq.py# публикация в RabbitMQ (задание 5)
│   │   ├── api/                # REST API, JWT-авторизация (задание 4)
│   │   ├── web/                # личный кабинет + админка на Jinja2 (задание 6)
│   │   └── monitoring.py       # бизнес-метрики Prometheus
│   └── tests/                  # 58 тестов + conftest (задание 7)
├── ml_worker/                  # воркер очереди с mDeBERTa (задание 5)
├── bot/                        # Telegram-бот на aiogram (asyncio)
├── monitoring/                 # Prometheus, Grafana, RabbitMQ с метриками
├── loadtest/                   # нагрузочный тест (async httpx)
├── web-proxy/                  # nginx (задание 2)
├── e2e/                        # сквозные тесты живого стека (задание 7)
├── docker-compose.yml
└── TESTING.md                  # отчёт о тестировании
```

## Доменная модель

- `User` / `Administrator` — пользователь с приватным балансом; изменения
  только через методы `credit()`/`debit()` с проверками. Админ подтверждает
  пополнения (`approve_top_up()`).
- `Transaction` (абстрактная) → `CreditTransaction` / `DebitTransaction` —
  полиморфное применение операции к балансу (`apply()`).
- `MLModel` (абстрактная, generic) → `EvidenceClassifierModel` →
  `KeywordEvidenceClassifierModel` (офлайн-заглушка для тестов) /
  `HuggingFaceEvidenceClassifierModel` (боевой zero-shot на mDeBERTa).
  Контракт: `validate_input()`, `predict()`; движок воркер выбирает
  по имени модели из каталога.
- `MLTask` — жизненный цикл пакетного запроса: валидация каждого элемента,
  стоимость только за валидные, проверка баланса, списание как
  `DebitTransaction` со ссылкой на задачу. Статусы: `created`, `validating`,
  `processing`, `completed`, `partially_completed`, `failed`.
- `EvidenceItem`, `CategoryScore`, `EvidenceMapping` — неизменяемые
  объекты-значения: вход, оценка категории, итоговый маппинг
  (основная категория, запасные, недостающие данные, флаг ручной проверки).
- `PredictionResult`, `BatchItemError`, `PredictionHistory`,
  `TransactionHistory` — итоги пакета и журналы операций.
