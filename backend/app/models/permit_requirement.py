import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.shipment import Shipment


class PermitRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One regulator's permit requirement for a shipment (architecture doc Section 6.3
    / 9), computed from its line items' effective HS codes against the versioned
    permit-rules data file (app/repositories/permit_rules_repository.py) — never
    persisted rule *content*, only the per-shipment *result* of applying those rules.
    Re-triaging a shipment replaces its rows outright (no per-row user state like
    Discrepancy's acknowledgment to preserve).
    """

    __tablename__ = "permit_requirements"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    regulator: Mapped[str] = mapped_column(String(100), nullable=False)
    permit_type: Mapped[str] = mapped_column(String(255), nullable=False)
    applies_to_line_items: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    estimated_processing_time_days: Mapped[int] = mapped_column(nullable=False)
    reference_link: Mapped[str] = mapped_column(Text, nullable=False)

    shipment: Mapped["Shipment"] = relationship(back_populates="permit_requirements")
