from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .enums import EvidenceCategory
from .ml_model import MLModel


@dataclass(frozen=True)
class EvidenceItem:
    """
    Одно достижение кандидата для классификации. Немутабельный объект
    """

    title: str
    description: str
    evidence_type: str | None = None
    source_url: str | None = None
    metrics: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class CategoryScore:
    category: EvidenceCategory
    confidence: float


@dataclass(frozen=True)
class CategoryScore:
    category: EvidenceCategory
    confidence: float


@dataclass(frozen=True)
class EvidenceMapping:
    """ Результат для единицы эвиденса """

    primary: CategoryScore
    secondary: tuple[CategoryScore, ...]
    missing_information: tuple[str, ...]
    human_review_required: bool


class EvidenceClassifierModel(MLModel[EvidenceItem, EvidenceMapping], ABC):
    """ Семейство классификаторов

        Зашаренные валидации и сборка результатов лежит здесь. Сам скоринг это хук (_classify_text)
        который заполняется конкретным движком. 
        На этапе прикрутки модели - это станет адаптером с HF
    """

    HUMAN_REVIEW_THRESHOLD = 0.80

    def validate_input(self, item: EvidenceItem) -> list[str]:
        errors: list[str] = []
        if not item.title.strip():
            errors.append("title is required")
        if len(item.description.strip()) < 40:
            errors.append('описание должно иметь минимум 40 символов')
        return errors

    def predict(self, item: EvidenceItem) -> EvidenceMapping:
        scores = self._classify_text(item.description)
        missing = self._find_missing_information(item)
        return EvidenceMapping(
            primary=scores[0],
            secondary=tuple(scores[1:3]),
            missing_information=tuple(missing),
            human_review_required=(
                scores[0].confidence < self.HUMAN_REVIEW_THRESHOLD or bool(missing)
            ),
        )


    @abstractmethod
    def _classify_text(self, text: str) -> list[CategoryScore]:
        ...

    def _find_missing_information(self, item: EvidenceItem) -> list[str]:
        missing: list[str] = []
        if not item.metrics:
            missing.append("не предъявлено измеримых метрик")
        if not item.source_url:
            missing.append("не предъявлен URL")
        return missing


class KeywordEvidenceClassifierModel(EvidenceClassifierModel):
    """ Детермнистик набор ключевых слов """

    _KEYWORDS = {
        EvidenceCategory.INNOVATION: ["founder", "built", "created", "invented", "novel", "startup", "product"],
        EvidenceCategory.RECOGNITION_LEADER: ["award", "keynote", "recognized", "leader", "invited"],
        EvidenceCategory.ACADEMIC_CONTRIBUTION: ["paper", "research", "published", "citation", "journal"],
        EvidenceCategory.SIGNIFICANT_CONTRIBUTION: ["revenue", "growth", "users", "impact", "scaled"],
        EvidenceCategory.OUTSIDE_WORK: ["mentoring", "open source", "volunteer", "community", "talk"],
    }

    def _classify_text(self, text: str) -> list[CategoryScore]:
        lowered = text.lower()
        scored: list[CategoryScore] = []
        total_hits = 0
        for category, words in self._KEYWORDS.items():
            hits = sum(1 for word in words if word in lowered)
            total_hits += hits
            confidence = min(0.5 + 0.12 * hits, 0.99) if hits else 0.2
            scored.append(CategoryScore(category, round(confidence, 2)))
        scored.sort(key=lambda score: score.confidence, reverse=True)
        if total_hits == 0:
            # текст ни с чем у модели не пересекается - нет сигнала
            return [CategoryScore(EvidenceCategory.INSUFFICIENT, 0.3), *scored[:2]]
        scored.append(CategoryScore(EvidenceCategory.IRRELEVANT, 0.1))
        return scored


class HuggingFaceEvidenceClassifierModel(EvidenceClassifierModel):
    """ будет в будущем как прикручу модель """

    def _classify_text(self, text: str) -> list[CategoryScore]:
        raise NotImplementedError(
            "zero-shot адаптер в будущем"
        )