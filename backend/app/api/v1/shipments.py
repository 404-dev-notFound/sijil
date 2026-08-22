import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids, get_current_user
from app.models.enums import DocumentType, ShipmentDirection, ShipmentStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.shipment import (
    DocumentCorrectionRequest,
    DocumentOut,
    DocumentUploadResponse,
    ShipmentCreateRequest,
    ShipmentDetailOut,
    ShipmentOut,
)
from app.services.document_service import DocumentService
from app.services.shipment_service import ShipmentService
from app.utils.exceptions import NotFoundError

router = APIRouter()

_SSE_MAX_STREAM_SECONDS = 120
_SSE_POLL_INTERVAL_SECONDS = 0.5
# needs_manual_review is a genuine stopping point requiring user action (a PATCH
# correction), not a transient state — the frontend reconnects afterward if it wants
# to keep watching. A shipment can still transition after analysis_complete /
# report_generated in later phases, but Phase 2 has nothing left to stream once one of
# these is reached.
_SSE_STOP_STATUSES = frozenset(
    {
        ShipmentStatus.NEEDS_MANUAL_REVIEW,
        ShipmentStatus.ANALYSIS_COMPLETE,
        ShipmentStatus.REPORT_GENERATED,
    }
)


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
        # A rough estimate for the response shape API SPEC Section 7 defines, not a
        # measured ETA — actual completion time depends on the configured OCR/LLM
        # provider's latency.
        estimated_completion_seconds=12,
    )


@router.get(
    "/{shipment_id}/documents/{document_id}",
    response_model=DocumentOut,
)
async def get_document(
    shipment_id: uuid.UUID,
    document_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    document = await DocumentService(db).get_document(
        shipment_id=shipment_id,
        document_id=document_id,
        accessible_company_ids=accessible_company_ids,
    )
    return DocumentOut.model_validate(document)


@router.patch(
    "/{shipment_id}/documents/{document_id}",
    response_model=DocumentOut,
)
async def correct_document(
    shipment_id: uuid.UUID,
    document_id: uuid.UUID,
    request: DocumentCorrectionRequest,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    document = await DocumentService(db).correct_extracted_fields(
        shipment_id=shipment_id,
        document_id=document_id,
        accessible_company_ids=accessible_company_ids,
        corrected_fields=request.extracted_fields,
    )
    return DocumentOut.model_validate(document)


@router.get("/{shipment_id}/events")
async def stream_shipment_events(
    shipment_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> StreamingResponse:
    """Server-Sent Events stream of a shipment's status transitions (API SPEC Section
    14) — lets the frontend show live processing status without aggressive polling.
    Raises the normal 404 (via the shared DomainError handler) if the shipment isn't
    accessible, before the stream itself ever opens; once streaming has started, an
    inaccessible/deleted shipment just ends the stream rather than trying to change an
    already-sent 200 status code.
    """
    service = ShipmentService(db)
    initial_status = await service.get_status(
        shipment_id, accessible_company_ids=accessible_company_ids
    )
    if initial_status is None:
        raise NotFoundError("Shipment not found.")

    async def _events() -> AsyncGenerator[str]:
        last_status = initial_status
        yield _sse_status_event(shipment_id, last_status)
        elapsed = 0.0
        while elapsed < _SSE_MAX_STREAM_SECONDS:
            if await request.is_disconnected():
                return
            await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)
            elapsed += _SSE_POLL_INTERVAL_SECONDS

            current_status = await service.get_status(
                shipment_id, accessible_company_ids=accessible_company_ids
            )
            if current_status is None:
                return
            if current_status != last_status:
                last_status = current_status
                yield _sse_status_event(shipment_id, last_status)
            if last_status in _SSE_STOP_STATUSES:
                return

    return StreamingResponse(_events(), media_type="text/event-stream")


def _sse_status_event(shipment_id: uuid.UUID, shipment_status: ShipmentStatus) -> str:
    data = json.dumps({"shipment_id": str(shipment_id), "status": shipment_status.value})
    return f"event: status_update\ndata: {data}\n\n"
