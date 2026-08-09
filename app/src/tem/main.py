"""REST API сервиса. Точка входа: uvicorn tem.main:app.

Роутеры сгруппированы как в рекомендации к заданию: auth, balance, predict,
history. На старте создаём таблицы и наполняем базу демо-данными
(seed идемпотентный, так что перезапуски безопасны).
"""
import logging

from fastapi import FastAPI
from sqlmodel import Session

from .api.auth import auth_route
from .api.balance import balance_route
from .api.history import history_route
from .api.predict import predict_route
from .infrastructure.db.database import engine, init_db
from .infrastructure.db.seed import seed

logger = logging.getLogger(__name__)


def create_application() -> FastAPI:
    app = FastAPI(
        title="Talent Evidence Mapper",
        version="0.3.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.include_router(auth_route, prefix="/api/auth", tags=["auth"])
    app.include_router(balance_route, prefix="/api/balance", tags=["balance"])
    app.include_router(predict_route, prefix="/api/predict", tags=["predict"])
    app.include_router(history_route, prefix="/api/history", tags=["history"])

    @app.get("/")
    def root() -> dict:
        return {"service": "talent-evidence-mapper", "status": "ok"}

    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy"}

    return app


app = create_application()


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Initializing database and seeding demo data...")
    init_db()
    with Session(engine) as session:
        seed(session)
        session.commit()