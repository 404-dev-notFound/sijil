from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# all-MiniLM-L6-v2 (app/integrations/embedding_client.py) — changing the embedding
# model requires re-embedding every row and updating this dimension together.
EMBEDDING_DIMENSIONS = 384


class TariffHeading(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The vector-search knowledge base ClassificationService searches against
    (architecture doc Section 6.1 / 9's TariffKnowledgeBaseRepository).

    seed_tariff_headings.py currently loads only a small, clearly-labeled illustrative
    set of public WCO 6-digit headings — NOT the real UAE/GCC 12-digit tariff schedule.
    Classification quality is entirely bounded by this table's completeness; real
    ingestion of the official schedule is a separate data-sourcing task (implementation
    plan Section 5 / Track A-style research), not something this scaffold fabricates.
    """

    __tablename__ = "tariff_headings"

    hs_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance flag distinguishing illustrative seed rows from a real ingested
    # schedule — never let a caller mistake placeholder data for authoritative data.
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
