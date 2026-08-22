import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import OriginQualificationStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.line_item import LineItem


class OriginDetermination(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One CEPA preferential-origin determination per line item (architecture doc
    Section 6.4 / 9) — one row per line item (line_item_id unique), overwritten in
    place by a re-determination (same "reconcile, don't accumulate" approach as
    ClassificationResult), never a growing history. local_content_value/total_value
    are the user-supplied value-content breakdown (API SPEC Section 11's POST
    .../origin/value-breakdown) — persisted so a re-determination after a
    reclassify/override doesn't need the user to resupply them.
    """

    __tablename__ = "origin_determinations"

    line_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("line_items.id"), nullable=False, unique=True, index=True
    )
    agreement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualifies: Mapped[OriginQualificationStatus] = mapped_column(
        Enum(OriginQualificationStatus, name="origin_qualification_status"), nullable=False
    )
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    required_documents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    estimated_duty_savings_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    estimated_duty_savings_currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )
    local_content_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    value_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    line_item: Mapped["LineItem"] = relationship(back_populates="origin_determination")
