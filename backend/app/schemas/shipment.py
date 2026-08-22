import uuid
from datetime import datetime
from typing import Any

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
    extracted_fields: dict[str, Any] | None = None
    extraction_confidence: float | None
    created_at: datetime


class ShipmentDetailOut(ShipmentOut):
    documents: list[DocumentOut] = []


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus
    estimated_completion_seconds: int


class DocumentCorrectionRequest(BaseModel):
    """Partial extracted_fields object with corrected values (API SPEC Section 7) —
    merged onto the document's existing extracted_fields, keyed the same way
    MockLLMClient.extract_document_fields names them (e.g. "invoice_number")."""

    extracted_fields: dict[str, Any]
