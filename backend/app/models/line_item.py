import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.classification_result import ClassificationResult
    from app.models.origin_determination import OriginDetermination
    from app.models.shipment import Shipment


class LineItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single product line derived from a shipment's commercial invoice (architecture
    doc Section 9) — created by the classification worker once the invoice document's
    extracted_fields.line_items are available (Phase 2 output), not created directly
    via the API.
    """

    __tablename__ = "line_items"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="line_items")
    classification: Mapped["ClassificationResult | None"] = relationship(
        back_populates="line_item", uselist=False, cascade="all, delete-orphan"
    )
    origin_determination: Mapped["OriginDetermination | None"] = relationship(
        back_populates="line_item", uselist=False, cascade="all, delete-orphan"
    )
