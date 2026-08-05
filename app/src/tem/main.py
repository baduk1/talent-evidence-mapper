"""Минимальная точка входа приложения.

На этом этапе API намеренно крошечный: его задача - доказать, что контейнер
запускается и что обратный прокси до него достукивается. Настоящие эндпоинты
(регистрация, баланс, ML-задачи) появятся на уроке про интерфейсы.
"""
from fastapi import FastAPI

app = FastAPI(title="Talent Evidence Mapper", version="0.2.0")


@app.get("/")
def root() -> dict:
    return {"service": "talent-evidence-mapper", "status": "ok"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}