import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids, get_current_user
from app.models.enums import DocumentType, ShipmentDirection, ShipmentStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.shipment import (
    DocumentUploadResponse,
    ShipmentCreateRequest,
    ShipmentDetailOut,
    ShipmentOut,
)
from app.services.document_service import DocumentService
from app.services.shipment_service import ShipmentService

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ShipmentOut)
async def create_shipment(
    request: ShipmentCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShipmentOut:
    shipment = await ShipmentService(db).create_shipment(
        request, user=user, accessible_company_ids=accessible_company_ids
    )
    return ShipmentOut.model_validate(shipment)


@router.get("", response_model=PaginatedResponse[ShipmentOut])
async def list_shipments(
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: ShipmentStatus | None = None,
    direction: ShipmentDirection | None = None,
    page: int = 1,
    page_size: int = 25,
) -> PaginatedResponse[ShipmentOut]:
    page_size = min(page_size, 100)
    shipments, total = await ShipmentService(db).list_shipments(
        accessible_company_ids=accessible_company_ids,
        status=status_filter,
        direction=direction,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.build(
        [ShipmentOut.model_validate(s) for s in shipments],
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.get("/{shipment_id}", response_model=ShipmentDetailOut)
async def get_shipment(
    shipment_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShipmentDetailOut:
    shipment = await ShipmentService(db).get_shipment(
        shipment_id, accessible_company_ids=accessible_company_ids
    )
    return ShipmentDetailOut.model_validate(shipment)


@router.post(
    "/{shipment_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentUploadResponse,
)
async def upload_document(
    shipment_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[DocumentType, Form()],
) -> DocumentUploadResponse:
    file_bytes = await file.read()
    document = await DocumentService(db).upload_document(
        shipment_id=shipment_id,
        accessible_company_ids=accessible_company_ids,
        doc_type=doc_type,
        filename=file.filename or "upload",
        file_bytes=file_bytes,
    )
    return DocumentUploadResponse(
        document_id=document.id,
        status=document.status,
        # No OCR/extraction pipeline yet (that's Phase 2) — this is a placeholder
        # estimate for the response shape API SPEC Section 7 defines; not a real ETA.
        estimated_completion_seconds=12,
    )
