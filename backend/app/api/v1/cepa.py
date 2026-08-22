import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids
from app.models.origin_determination import OriginDetermination
from app.schemas.line_item import MoneyOut
from app.schemas.origin_determination import OriginDeterminationOut, ValueBreakdownRequest
from app.services.origin_service import OriginService

router = APIRouter()


def _to_origin_out(determination: OriginDetermination) -> OriginDeterminationOut:
    estimated_duty_savings = None
    if determination.estimated_duty_savings_amount is not None:
        estimated_duty_savings = MoneyOut(
            amount=str(determination.estimated_duty_savings_amount),
            currency=determination.estimated_duty_savings_currency or "",
        )
    return OriginDeterminationOut(
        line_item_id=determination.line_item_id,
        agreement=determination.agreement,
        qualifies=determination.qualifies,
        reasoning=determination.reasoning,
        required_documents=determination.required_documents,
        missing_fields=determination.missing_fields,
        estimated_duty_savings=estimated_duty_savings,
    )


@router.get(
    "/{shipment_id}/line-items/{line_item_id}/origin",
    response_model=OriginDeterminationOut,
)
async def get_origin_determination(
    shipment_id: uuid.UUID,
    line_item_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OriginDeterminationOut:
    determination = await OriginService(db).get_origin(
        shipment_id=shipment_id,
        line_item_id=line_item_id,
        accessible_company_ids=accessible_company_ids,
    )
    return _to_origin_out(determination)


@router.post(
    "/{shipment_id}/line-items/{line_item_id}/origin/value-breakdown",
    response_model=OriginDeterminationOut,
)
async def submit_value_breakdown(
    shipment_id: uuid.UUID,
    line_item_id: uuid.UUID,
    request: ValueBreakdownRequest,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OriginDeterminationOut:
    determination = await OriginService(db).submit_value_breakdown(
        shipment_id=shipment_id,
        line_item_id=line_item_id,
        accessible_company_ids=accessible_company_ids,
        local_content_value=request.local_content_value.amount,
        total_value=request.total_value.amount,
        currency=request.total_value.currency,
    )
    return _to_origin_out(determination)
