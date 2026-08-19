import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    DocumentStatus,
    DocumentType,
    ShipmentDirection,
    ShipmentStatus,
)


class ShipmentCreateRequest(BaseModel):
    direction: ShipmentDirection
    on_behalf_of_company_id: uuid.UUID | None = None
    notes: str | None = None


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    direction: ShipmentDirection
    status: ShipmentStatus
    notes: str | None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shipment_id: uuid.UUID
    doc_type: DocumentType
    status: DocumentStatus
    original_filename: str
    content_type: str
    size_bytes: int
    extraction_confidence: float | None
    created_at: datetime


class ShipmentDetailOut(ShipmentOut):
    documents: list[DocumentOut] = []


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus
    estimated_completion_seconds: int
