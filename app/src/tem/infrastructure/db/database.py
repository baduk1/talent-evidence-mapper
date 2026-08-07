from sqlmodel import SQLModel, Session, create_engine

from .config import get_settings


def get_database_engine():
    """Создать движок SQLAlchemy по настройкам из env."""
    settings = get_settings()
    return create_engine(
        url=settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_pre_ping=True,
    )


engine = get_database_engine()


def get_session():
    with Session(engine) as session:
        yield session


def init_db(drop_all: bool = False) -> None:
    """Создать таблицы. drop_all=True сначала всё удаляет (для экспериментов)."""
    if drop_all:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)