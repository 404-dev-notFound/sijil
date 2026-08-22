import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.line_item import LineItem


class ClassificationResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One HS classification per line item (architecture doc Section 6.1 / 9). A
    reclassify overwrites hs_code/confidence/reasoning/alternatives in place rather
    than creating a second row — line_item_id is unique, one result per line item —
    but user_override_hs_code is never overwritten by a reclassify, only by a new
    explicit override (both the AI suggestion and the override are retained for
    audit purposes, per API SPEC Section 8).
    """

    __tablename__ = "classification_results"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_classification_results_confidence_range",
        ),
    )

    line_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("line_items.id"), nullable=False, unique=True, index=True
    )
    hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    requires_manual_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # [{"hs_code": ..., "confidence": ...}, ...] — API SPEC Section 8's alternatives list.
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    user_override_hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    line_item: Mapped["LineItem"] = relationship(back_populates="classification")
