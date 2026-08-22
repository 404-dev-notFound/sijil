import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ShipmentDirection, ShipmentStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.discrepancy import Discrepancy
    from app.models.document import Document
    from app.models.line_item import LineItem
    from app.models.permit_requirement import PermitRequirement
    from app.models.report import Report


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
    # Country names (not ISO codes — kept simple, matched against
    # data/cepa_rules/rules_v1.json's origin_country/destination_country fields as
    # plain strings). Nullable: Phases 1-5 never needed this; CEPAOriginService
    # (Phase 6) can't determine an applicable agreement without it, so a shipment
    # missing these just yields NOT_APPLICABLE for every line item rather than an
    # error (architecture doc Section 6.4's inputs: "HS code, origin country,
    # destination country, value-content breakdown").
    origin_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    destination_country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    discrepancies: Mapped[list["Discrepancy"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    permit_requirements: Mapped[list["PermitRequirement"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
