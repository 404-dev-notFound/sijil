import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ReportStatus


class ReportTriggerResponse(BaseModel):
    report_id: uuid.UUID
    status: ReportStatus


class ReportOut(BaseModel):
    id: uuid.UUID
    shipment_id: uuid.UUID
    status: ReportStatus
    download_url: str | None
    generated_at: datetime | None
