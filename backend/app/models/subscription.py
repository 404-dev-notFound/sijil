import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SubscriptionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company import Company


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One company's billing subscription (architecture doc Section 9 / API SPEC
    Section 13) — company_id is unique, one subscription per company. Created and
    updated exclusively by billing-provider webhook events (app/services/
    billing_service.py), never directly from a user request; POST /billing/checkout
    only starts a hosted checkout session, it doesn't create this row itself.
    shipments_used_this_period is deliberately not a stored column — it's derived by
    counting the company's shipments created since current_period_start, so it can
    never drift out of sync with the shipments table.
    """

    __tablename__ = "subscriptions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), nullable=False
    )
    billing_provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipments_included_per_month: Mapped[int] = mapped_column(nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    company: Mapped["Company"] = relationship(back_populates="subscription")
