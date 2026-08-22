import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DiscrepancySeverity


class DiscrepancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field: str
    severity: DiscrepancySeverity
    documents_involved: list[str]
    description: str
    suggested_resolution: str
    acknowledged: bool
    acknowledged_at: datetime | None
