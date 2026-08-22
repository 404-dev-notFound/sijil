import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ReportStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.shipment import Shipment


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A generated compliance-report PDF bundling classification, discrepancies,
    permits, and origin results for one shipment (architecture doc Section 9 / API
    SPEC Section 12). Each POST /shipments/{id}/report creates a new row rather than
    overwriting a prior one — old reports stay retrievable by their own id, a report
    history rather than a single mutable slot.
    """

    __tablename__ = "reports"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.GENERATING
    )
    # Object-storage key, not a public URL — same "never served directly from a public
    # bucket" rule as Document.storage_path (architecture doc Section 15). Null until
    # generation succeeds.
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="reports")
