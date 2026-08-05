from decimal import Decimal

from sqlmodel import Session

from ...domain.enums import UserRole
from . import crud
from .database import engine, init_db


def seed(session: Session) -> None:
    """Демо-данные. Идемпотентно: повторный запуск не дублирует строки
    и не ломает существующие данные."""
    if crud.get_user_by_email(session, "user@example.com") is None:
        crud.create_user(
            session, "user@example.com", "demo-hash",
            role=UserRole.USER, balance=Decimal("20"),
        )
    if crud.get_user_by_email(session, "admin@example.com") is None:
        crud.create_user(
            session, "admin@example.com", "demo-hash",
            role=UserRole.ADMIN, balance=Decimal("0"),
        )

    existing = {(model.name, model.version) for model in crud.list_active_models(session)}
    catalog = [
        ("Keyword evidence classifier", "0.1", Decimal("1")),
        ("mDeBERTa zero-shot classifier", "0.1", Decimal("1")),
    ]
    for name, version, cost in catalog:
        if (name, version) not in existing:
            crud.add_model(session, name, version, credit_cost=cost)


def main() -> None:
    init_db()
    with Session(engine) as session:
        seed(session)
        session.commit()
    print("Database initialized with demo data")


if __name__ == "__main__":
    main()