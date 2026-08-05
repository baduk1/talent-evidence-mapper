from decimal import Decimal

from tem.domain.evidence import EvidenceItem, KeywordEvidenceClassifierModel
from tem.domain.task import MLTask
from tem.domain.user import User


def make_setup(balance: str = "10"):
    user = User(email="a@b.com", _password_hash="h")
    if Decimal(balance) > 0:
        user.credit(Decimal(balance))
    model = KeywordEvidenceClassifierModel(
        "kw-1", "Keyword", "Offline keyword baseline", "0.1", Decimal("1")
    )
    return user, model


def valid_item(index: int = 0) -> EvidenceItem:
    return EvidenceItem(
        title=f"Item {index}",
        description=(
            "I created and maintain an open source library with measurable impact "
            "and many users"
        ),
    )


def invalid_item() -> EvidenceItem:
    return EvidenceItem(title="", description="short")


def test_validate_separates_valid_and_invalid():
    user, model = make_setup()
    task = MLTask(user, model, [valid_item(1), invalid_item(), valid_item(2)])
    valid, errors = task.validate()
    assert len(valid) == 2
    assert len(errors) == 1
    assert errors[0].item_index == 1


def test_estimated_cost_covers_all_items():
    user, model = make_setup()
    task = MLTask(user, model, [valid_item(1), invalid_item()])
    assert task.estimated_cost() == Decimal("2")