# Import every model module here so Base.metadata is complete for Alembic autogenerate
# (alembic/env.py imports this package).
from app.models.base import Base
from app.models.classification_result import ClassificationResult
from app.models.company import Company
from app.models.discrepancy import Discrepancy
from app.models.document import Document
from app.models.line_item import LineItem
from app.models.permit_requirement import PermitRequirement
from app.models.shipment import Shipment
from app.models.tariff_heading import TariffHeading
from app.models.user import User

__all__ = [
    "Base",
    "ClassificationResult",
    "Company",
    "Discrepancy",
    "Document",
    "LineItem",
    "PermitRequirement",
    "Shipment",
    "TariffHeading",
    "User",
]
