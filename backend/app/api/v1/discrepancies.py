import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids, get_current_user
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.discrepancy import DiscrepancyOut
from app.services.discrepancy_service import DiscrepancyService

router = APIRouter()


@router.get("/{shipment_id}/discrepancies", response_model=PaginatedResponse[DiscrepancyOut])
async def list_discrepancies(
    shipment_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[DiscrepancyOut]:
    discrepancies = await DiscrepancyService(db).list_discrepancies(
        shipment_id, accessible_company_ids=accessible_company_ids
    )
    out = [DiscrepancyOut.model_validate(discrepancy) for discrepancy in discrepancies]
    # No real page/offset pagination in the repository — a shipment's discrepancies
    # are naturally bounded (one comparison rule per field), same rationale as
    # classification.py's list_line_items.
    return PaginatedResponse.build(out, page=1, page_size=100, total_items=len(out))


@router.post(
    "/{shipment_id}/discrepancies/{discrepancy_id}/acknowledge",
    response_model=DiscrepancyOut,
)
async def acknowledge_discrepancy(
    shipment_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiscrepancyOut:
    discrepancy = await DiscrepancyService(db).acknowledge(
        shipment_id=shipment_id,
        discrepancy_id=discrepancy_id,
        accessible_company_ids=accessible_company_ids,
        user_id=user.id,
    )
    return DiscrepancyOut.model_validate(discrepancy)
