import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ShipmentDirection, ShipmentStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.line_item import LineItem


class Shipment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shipments"
    __table_args__ = (
        # "All shipments for a company, most recent first" — architecture doc Section 9
        # query patterns.
        Index("ix_shipments_company_id_created_at", "company_id", "created_at"),
    )

    # Non-null, indexed FK — every query must be scoped by this (architecture doc
    # Section 14). Repositories enforce it; this column is what makes that possible.
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    direction: Mapped[ShipmentDirection] = mapped_column(
        Enum(ShipmentDirection, name="shipment_direction"), nullable=False
    )
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus, name="shipment_status"),
        nullable=False,
        default=ShipmentStatus.CREATED,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
