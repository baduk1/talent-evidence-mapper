from decimal import Decimal

from tem.domain.enums import EvidenceCategory
from tem.domain.evidence import (
    EvidenceItem,
    EvidenceMapping,
    KeywordEvidenceClassifierModel,
)


def make_model() -> KeywordEvidenceClassifierModel:
    return KeywordEvidenceClassifierModel(
        model_id='kw-1',
        name="Keyword classifier",
        description="Offline keyword baseline",
        version="0.1",
        credit_cost=Decimal("1")
    )


def test_model_metadata_is_exposed():
    model = make_model()
    assert model.model_id == "kw-1"
    assert model.description == "Offline keyword baseline"
    assert model.credit_cost == Decimal("1")


def test_validate_input_flags_short_description():
    model = make_model()
    item = EvidenceItem(title="X", description="too short")
    errors = model.validate_input(item)
    assert any("минимум 40 символов" in error for error in errors)


def test_validate_input_flags_missing_title():
    model = make_model()
    item = EvidenceItem(title="  ", description="A long enough description to pass the length check")
    assert "title is required" in model.validate_input(item)


def test_valid_item_passes_validation():
    model = make_model()
    item = EvidenceItem(
        title="OSS",
        description="I created and maintain an open source observability library used widely",
    )
    assert model.validate_input(item) == []


def test_predict_returns_mapping():
    model = make_model()
    item = EvidenceItem(
        title="OSS",
        description=(
            "I created and maintain an open source observability library with many "
            "contributors and stars"
        ),
    )
    mapping = model.predict(item)
    assert isinstance(mapping, EvidenceMapping)
    assert mapping.primary.category in EvidenceCategory
    assert len(mapping.secondary) == 2
    assert mapping.missing_information 
    assert mapping.human_review_required


def test_unmatched_text_is_flagged_insufficient():
    model = make_model()
    item = EvidenceItem(
        title="Hobby",
        description="I enjoy long walks on the beach and cooking pasta every weekend",
    )
    mapping = model.predict(item)
    assert mapping.primary.category == EvidenceCategory.INSUFFICIENT
    assert mapping.human_review_required