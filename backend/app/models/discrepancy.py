import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import DiscrepancySeverity
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.shipment import Shipment


class Discrepancy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A cross-document inconsistency for one shipment (architecture doc Section 6.2 /
    9). `field` is the natural key ConsistencyService re-evaluates against on every
    re-run (app/services/consistency_service.py) — one row per comparison rule per
    shipment, updated in place rather than duplicated, so a user's acknowledgment
    survives a re-check unless the underlying discrepancy disappears entirely.
    """

    __tablename__ = "discrepancies"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[DiscrepancySeverity] = mapped_column(
        Enum(DiscrepancySeverity, name="discrepancy_severity"), nullable=False
    )
    # Document IDs as strings, not a join table — a comparison rule only ever
    # involves a small, fixed number of documents (API SPEC Section 9's example).
    documents_involved: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_resolution: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(nullable=False, default=False)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    shipment: Mapped["Shipment"] = relationship(back_populates="discrepancies")
