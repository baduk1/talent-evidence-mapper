"""Бизнес-метрики сервиса в формате Prometheus.

Технические HTTP-метрики (RPS, латентность, коды) собирает
prometheus-fastapi-instrumentator на /metrics. Здесь - третий уровень,
бизнес-события: регистрации, пополнения, ML-задачи.
"""
from prometheus_client import Counter

SIGNUPS_TOTAL = Counter("tem_signups_total", "Регистрации пользователей")
TOPUPS_TOTAL = Counter("tem_topups_total", "Пополнения баланса")
PREDICTIONS_TOTAL = Counter("tem_predictions_total", "Принятые ML-задачи")
