# Import every model module here so Base.metadata is complete for Alembic autogenerate
# (alembic/env.py imports this package).
from app.models.base import Base
from app.models.company import Company
from app.models.document import Document
from app.models.shipment import Shipment
from app.models.user import User

__all__ = ["Base", "Company", "Document", "Shipment", "User"]
