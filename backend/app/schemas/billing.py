from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SubscriptionStatus


class CheckoutRequest(BaseModel):
    plan: str = Field(min_length=1, max_length=50)


class CheckoutResponse(BaseModel):
    checkout_url: str


class SubscriptionOut(BaseModel):
    plan: str
    status: SubscriptionStatus
    shipments_included_per_month: int
    shipments_used_this_period: int
    current_period_start: datetime
    current_period_end: datetime
