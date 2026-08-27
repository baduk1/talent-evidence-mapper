"""HF-адаптер: маппинг скоров в категории и правила insufficient.

Настоящей модели и transformers в тестовом окружении нет - пайплайн
подменяем заглушкой с заданными скорами.
"""
from decimal import Decimal

import pytest

from tem.domain.enums import EvidenceCategory
from tem.domain.evidence import EvidenceItem, HuggingFaceEvidenceClassifierModel

# Порядок соответствует _HYPOTHESES: innovation, recognition_leader,
# significant_contribution, academic_contribution, outside_work.
CONFIDENT = [0.9, 0.05, 0.03, 0.01, 0.01]
FLAT = [0.2, 0.2, 0.2, 0.2, 0.2]
CLOSE_CALL = [0.40, 0.38, 0.10, 0.07, 0.05]


class FakePipeline:
    """Имитирует ответ transformers pipeline: метки по убыванию скора."""

    def __init__(self, scores: list[float]):
        self.scores = scores

    def __call__(self, text, candidate_labels, hypothesis_template, multi_label):
        order = sorted(range(len(candidate_labels)), key=lambda i: -self.scores[i])
        return {
            "labels": [candidate_labels[i] for i in order],
            "scores": [self.scores[i] for i in order],
        }


@pytest.fixture()
def make_model(monkeypatch):
    def make(scores: list[float]) -> HuggingFaceEvidenceClassifierModel:
        monkeypatch.setattr(
            HuggingFaceEvidenceClassifierModel, "_pipeline", FakePipeline(scores)
        )
        return HuggingFaceEvidenceClassifierModel(
            model_id="hf-1",
            name="mDeBERTa zero-shot classifier",
            description="",
            version="0.1",
            credit_cost=Decimal("1"),
        )
    return make


def item() -> EvidenceItem:
    return EvidenceItem(
        title="OSS library",
        description=(
            "I created and maintain an open source observability library "
            "with measurable impact and many users"
        ),
    )


def test_confident_scores_mapped_to_categories(make_model):
    model = make_model(CONFIDENT)
    mapping = model.predict(item())
    assert mapping.primary.category == EvidenceCategory.INNOVATION
    assert mapping.primary.confidence == 0.9
    assert len(mapping.secondary) == 2
    # Второе место - recognition_leader, третье - significant_contribution
    assert mapping.secondary[0].category == EvidenceCategory.RECOGNITION_LEADER


def test_flat_distribution_is_insufficient(make_model):
    model = make_model(FLAT)
    mapping = model.predict(item())
    assert mapping.primary.category == EvidenceCategory.INSUFFICIENT
    assert mapping.human_review_required


def test_close_margin_is_insufficient(make_model):
    """Сильный top-скор, но крошечный отрыв - ответу не доверяем."""
    model = make_model(CLOSE_CALL)
    mapping = model.predict(item())
    assert mapping.primary.category == EvidenceCategory.INSUFFICIENT
    assert mapping.human_review_required
