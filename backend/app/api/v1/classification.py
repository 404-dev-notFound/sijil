import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids
from app.models.line_item import LineItem
from app.schemas.common import PaginatedResponse
from app.schemas.line_item import (
    ClassificationCandidateOut,
    ClassificationOut,
    ClassificationOverrideRequest,
    LineItemOut,
    MoneyOut,
    ReclassifyResponse,
    TopCandidateOut,
)
from app.services.line_item_service import LineItemService
from app.utils.exceptions import NotFoundError

router = APIRouter()


def _to_line_item_out(item: LineItem) -> LineItemOut:
    unit_value = None
    if item.unit_value is not None and item.currency is not None:
        unit_value = MoneyOut(amount=str(item.unit_value), currency=item.currency)

    classification = None
    if item.classification is not None:
        result = item.classification
        classification = ClassificationOut(
            top_candidate=TopCandidateOut(
                hs_code=result.hs_code, confidence=result.confidence, reasoning=result.reasoning
            ),
            alternatives=[
                ClassificationCandidateOut(**alternative) for alternative in result.alternatives
            ],
            requires_manual_review=result.requires_manual_review,
            user_override_hs_code=result.user_override_hs_code,
        )

    return LineItemOut(
        id=item.id,
        description=item.description,
        quantity=str(item.quantity) if item.quantity is not None else None,
        unit_value=unit_value,
        classification=classification,
    )


@router.get("/{shipment_id}/line-items", response_model=PaginatedResponse[LineItemOut])
async def list_line_items(
    shipment_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[LineItemOut]:
    items = await LineItemService(db).list_line_items(
        shipment_id, accessible_company_ids=accessible_company_ids
    )
    out = [_to_line_item_out(item) for item in items]
    # No real page/offset pagination in the repository — a shipment's line items are
    # naturally bounded (one invoice's worth of products), so returning them all under
    # the standard paginated envelope (API SPEC Section 8) is enough for now.
    return PaginatedResponse.build(out, page=1, page_size=100, total_items=len(out))


@router.get(
    "/{shipment_id}/line-items/{line_item_id}/classification",
    response_model=ClassificationOut,
)
async def get_line_item_classification(
    shipment_id: uuid.UUID,
    line_item_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassificationOut:
    item = await LineItemService(db).get_line_item(
        shipment_id, line_item_id, accessible_company_ids=accessible_company_ids
    )
    out = _to_line_item_out(item)
    if out.classification is None:
        raise NotFoundError("This line item has not been classified yet.")
    return out.classification


@router.post(
    "/{shipment_id}/line-items/{line_item_id}/override",
    response_model=LineItemOut,
)
async def override_classification(
    shipment_id: uuid.UUID,
    line_item_id: uuid.UUID,
    request: ClassificationOverrideRequest,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LineItemOut:
    item = await LineItemService(db).override_classification(
        shipment_id=shipment_id,
        line_item_id=line_item_id,
        accessible_company_ids=accessible_company_ids,
        hs_code=request.hs_code,
        reason=request.reason,
    )
    return _to_line_item_out(item)


@router.post(
    "/{shipment_id}/line-items/{line_item_id}/reclassify",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReclassifyResponse,
)
async def reclassify_line_item(
    shipment_id: uuid.UUID,
    line_item_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReclassifyResponse:
    await LineItemService(db).trigger_reclassify(
        shipment_id=shipment_id,
        line_item_id=line_item_id,
        accessible_company_ids=accessible_company_ids,
    )
    return ReclassifyResponse()
