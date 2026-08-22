import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids
from app.schemas.permit_requirement import PermitRequirementOut, PermitsResponse
from app.services.permit_service import PermitService

router = APIRouter()


@router.get("/{shipment_id}/permits", response_model=PermitsResponse)
async def list_permits(
    shipment_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PermitsResponse:
    permits = await PermitService(db).list_permits(
        shipment_id, accessible_company_ids=accessible_company_ids
    )
    items = [PermitRequirementOut.model_validate(permit) for permit in permits]
    # Explicit no_permits_required rather than an ambiguous empty list (API SPEC
    # Section 10 / architecture doc Section 2.4).
    return PermitsResponse(items=items, no_permits_required=len(items) == 0)
