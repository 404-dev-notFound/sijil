import uuid

from pydantic import BaseModel


class MoneyOut(BaseModel):
    amount: str
    currency: str


class ClassificationCandidateOut(BaseModel):
    hs_code: str
    confidence: float


class TopCandidateOut(BaseModel):
    hs_code: str | None
    confidence: float
    reasoning: str


class ClassificationOut(BaseModel):
    top_candidate: TopCandidateOut
    alternatives: list[ClassificationCandidateOut]
    requires_manual_review: bool
    user_override_hs_code: str | None


class LineItemOut(BaseModel):
    id: uuid.UUID
    description: str
    quantity: str | None
    unit_value: MoneyOut | None
    classification: ClassificationOut | None


class ClassificationOverrideRequest(BaseModel):
    hs_code: str
    reason: str | None = None


class ReclassifyResponse(BaseModel):
    status: str = "processing"
