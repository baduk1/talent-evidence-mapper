"""Pydantic-схемы запросов и ответов REST API."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SignUpRequest(BaseModel):
    email: str
    password: str


class SignInRequest(BaseModel):
    email: str
    password: str


class BalanceResponse(BaseModel):
    user_id: str
    balance: Decimal


class TopUpRequest(BaseModel):
    user_id: str
    amount: Decimal


class EvidenceItemIn(BaseModel):
    """Одно доказательство из запроса на предсказание."""

    title: str
    description: str
    evidence_type: str | None = None
    source_url: str | None = None
    metrics: dict[str, float | int | str] = {}


class PredictRequest(BaseModel):
    user_id: str
    items: list[EvidenceItemIn]
    model_id: str | None = None  # не передали - берём первую активную


class CategoryScoreOut(BaseModel):
    category: str
    confidence: float


class PredictionOut(BaseModel):
    title: str
    primary: CategoryScoreOut
    secondary: list[CategoryScoreOut]
    missing_information: list[str]
    human_review_required: bool


class InvalidItemOut(BaseModel):
    item_index: int
    messages: list[str]


class PredictResponse(BaseModel):
    task_id: str
    status: str
    predictions: list[PredictionOut]
    invalid_items: list[InvalidItemOut]
    credits_charged: Decimal
    balance: Decimal


class TaskHistoryEntry(BaseModel):
    task_id: str
    model_id: str
    status: str
    credits_charged: Decimal
    created_at: datetime


class TransactionEntry(BaseModel):
    id: str
    amount: Decimal
    type: str
    task_id: str | None
    created_at: datetime