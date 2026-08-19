from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models.

    Domain models (Company, User, Shipment, Document, ...) are added starting Phase 1 —
    see architecture doc Section 9 for the full data model.
    """
