# Тестирование системы (задание 7)

Два уровня: автоматические тесты (pytest, 52 шт.) и сквозной прогон против
живого docker-стека (e2e/e2e_check.py).

## Автоматические тесты

Запуск: `cd app && pytest -q` — 52 теста, все зелёные.

| Сценарий из задания | Чем покрыт |
| --- | --- |
| Создание пользователя | test_api.py::test_signup_and_signin_returns_token, test_orm.py::test_create_and_load_user |
| Авторизация и повторная авторизация | test_api.py::test_signup_and_signin_returns_token, test_signin_twice_both_tokens_work |
| Ошибки при неверных данных | test_api.py::test_signin_wrong_password, test_signup_duplicate_email_conflict, test_garbage_token_rejected |
| Получение и пополнение баланса | test_api.py::test_balance_topup_flow, test_orm.py::test_top_up_and_charge |
| Успешное списание за ML-запрос | test_worker.py::test_worker_processes_task_and_charges |
| Запрет списания при недостатке средств | test_worker.py::test_worker_fails_task_when_balance_is_low |
| Отсутствие списания при ошибке запроса | test_worker.py::test_worker_all_invalid_batch_charges_nothing |
| Отправка данных и получение результата | test_api.py::test_predict_queues_task_and_publishes_message + e2e |
| Некорректные и частично валидные данные | test_worker.py::test_worker_marks_partial_batch_and_charges_only_valid |
| История транзакций и ML-запросов | test_api.py::test_history_endpoints_show_only_own_data, test_orm.py::test_history_present_and_ordered |
| Веб-интерфейс | test_web.py (6 тестов: страницы, формы, cookie-авторизация) |
| Доменные правила | 24 теста (баланс, транзакции, задачи, классификатор, истории) |

## Сквозной прогон (end-to-end)

Стек: `docker-compose up -d --scale ml_worker=2`, затем `python e2e/e2e_check.py`.
Скрипт идёт по-настоящему сквозным путём: HTTP -> nginx -> FastAPI ->
RabbitMQ -> воркер -> Postgres -> HTTP. 20 проверок, все PASS:

- health, регистрация, дубль email (409), неверный пароль (403);
- авторизация и повторная авторизация (оба токена работают);
- баланс 0 -> пополнение на 5 -> баланс 5.00; отрицательное пополнение (400);
- батч из валидного и невалидного item: статус partially_completed,
  1 результат, 1 отклонённый item с причиной, списан 1 кредит, баланс 4.00;
- 5 валидных items при балансе 4: задача failed, списания нет;
- история транзакций (credit 5.00, debit 1.00) и история запросов
  (обе задачи со статусами).

## Выводы

- Критичные сценарии (деньги и обработка данных) покрыты на обоих уровнях:
  юнит/интеграционном и сквозном.
- Бизнес-инварианты подтверждены: списание только за обработанные данные,
  баланс неотрицательный, чужие данные недоступны (JWT).
- Найденная на прогоне проблема: при одновременном старте сервисов nginx
  мог закэшировать устаревший адрес app (лечится restart web-proxy).
