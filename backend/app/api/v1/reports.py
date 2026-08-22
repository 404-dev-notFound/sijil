import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_accessible_company_ids
from app.schemas.report import ReportOut
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: uuid.UUID,
    accessible_company_ids: Annotated[list[uuid.UUID], Depends(get_accessible_company_ids)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReportOut:
    report, download_url = await ReportService(db).get_report(
        report_id, accessible_company_ids=accessible_company_ids
    )
    return ReportOut(
        id=report.id,
        shipment_id=report.shipment_id,
        status=report.status,
        download_url=download_url,
        generated_at=report.generated_at,
    )
