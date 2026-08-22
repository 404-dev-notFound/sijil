import uuid
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.models.enums import OriginQualificationStatus
from app.schemas.line_item import MoneyOut


class OriginDeterminationOut(BaseModel):
    line_item_id: uuid.UUID
    agreement: str | None
    # A string enum, not the literal true/false/"insufficient_data" mix API SPEC
    # Section 11's example shows — a field that's sometimes a bool and sometimes a
    # string is worse API design than the spec's own prose actually calls for
    # (explicitly a 3-state — this codebase's own NOT_APPLICABLE makes it 4). See
    # app/models/enums.py's OriginQualificationStatus docstring.
    qualifies: OriginQualificationStatus
    reasoning: str
    required_documents: list[str]
    missing_fields: list[str]
    estimated_duty_savings: MoneyOut | None


class MoneyIn(BaseModel):
    """A request-side money field, unlike MoneyOut — Pydantic validates/coerces
    `amount` into a real Decimal here (a clean 422 on a malformed number), rather than
    an app-level exception risk from parsing a display string by hand later."""

    amount: Decimal
    currency: str


class ValueBreakdownRequest(BaseModel):
    local_content_value: MoneyIn
    total_value: MoneyIn

    @model_validator(mode="after")
    def _currencies_must_match(self) -> "ValueBreakdownRequest":
        if self.local_content_value.currency != self.total_value.currency:
            raise ValueError(
                "local_content_value and total_value must be in the same currency."
            )
        return self
