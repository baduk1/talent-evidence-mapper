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
class EvidenceMapping:
    """ Результат для единицы эвиденса """

    primary: CategoryScore
    secondary: tuple[CategoryScore, ...]
    missing_information: tuple[str, ...]
    human_review_required: bool


class EvidenceClassifierModel(MLModel[EvidenceItem, EvidenceMapping], ABC):
    """ Семейство классификаторов

        Зашаренные валидации и сборка результатов лежит здесь. Сам скоринг это хук (_classify_text)
        который заполняется конкретным движком (keyword-заглушка или HF zero-shot).
    """

    # Откалибровано под softmax mDeBERTa по 5 меткам: типичный top-скор
    # уверенного текста 0.6-0.95, ниже 0.6 - сигнал слабый, проверяет человек.
    HUMAN_REVIEW_THRESHOLD = 0.60

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
    """ Zero-shot классификатор на HuggingFace: mDeBERTa, дообученная на
        MNLI + XNLI (15 языков, включая русский). Текст - посылка, описание
        категории - гипотеза; скор метки = вероятность entailment.

        transformers/torch импортируются лениво, пайплайн кэшируется на
        процесс: домен работает и без ML-библиотек (тесты, demo), а воркер
        загружает веса (~1 ГБ) один раз при старте.
    """

    MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"

    # NLI-гипотезы подаём развёрнутыми описаниями - zero-shot так точнее,
    # чем по голым именам меток.
    _HYPOTHESES = {
        EvidenceCategory.INNOVATION: (
            "founding a startup, inventing a technology, or creating a new product"
        ),
        EvidenceCategory.RECOGNITION_LEADER: (
            "awards, keynotes, invited expert roles, or public leadership recognition"
        ),
        EvidenceCategory.SIGNIFICANT_CONTRIBUTION: (
            "measurable business impact such as revenue, growth, users, or scale"
        ),
        EvidenceCategory.ACADEMIC_CONTRIBUTION: (
            "scientific papers, research, citations, or academic publications"
        ),
        EvidenceCategory.OUTSIDE_WORK: (
            "mentoring, open source, community work, or volunteering outside the job"
        ),
    }

    # Правила «мало сигнала» поверх softmax по 5 меткам: совсем плоский
    # максимум или крошечный отрыв от второй метки - ответу нельзя доверять.
    # 0.30: реальный, но размытый текст (~0.34) ещё получает категорию.
    INSUFFICIENT_MAX_SCORE = 0.30
    INSUFFICIENT_MARGIN = 0.08

    _pipeline = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Грузим веса сразу: если transformers не установлен, ImportError
        # вылетит здесь - воркер переключится на keyword-движок.
        self._pipeline = self._get_pipeline()

    @classmethod
    def _get_pipeline(cls):
        if cls._pipeline is None:
            from transformers import pipeline

            cls._pipeline = pipeline(
                "zero-shot-classification", model=cls.MODEL_ID, device=-1
            )
        return cls._pipeline

    def _classify_text(self, text: str) -> list[CategoryScore]:
        result = self._pipeline(
            text,
            candidate_labels=list(self._HYPOTHESES.values()),
            hypothesis_template="This professional achievement is about {}.",
            multi_label=False,
        )
        scores_by_label = dict(zip(result["labels"], result["scores"]))
        scored = sorted(
            (
                CategoryScore(category, round(float(scores_by_label[hypothesis]), 4))
                for category, hypothesis in self._HYPOTHESES.items()
            ),
            key=lambda score: score.confidence,
            reverse=True,
        )
        top, second = scored[0].confidence, scored[1].confidence
        if top < self.INSUFFICIENT_MAX_SCORE or top - second < self.INSUFFICIENT_MARGIN:
            return [
                CategoryScore(EvidenceCategory.INSUFFICIENT, round(1.0 - top, 4)),
                *scored[:2],
            ]
        return scored