import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.integrations.object_storage import ObjectStorageClient
from app.models.enums import ReportStatus
from app.models.report import Report
from app.repositories.report_repository import ReportRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.utils.exceptions import NotFoundError
from app.workers.celery_app import celery_app


class ReportService:
    """API-facing, tenant-scoped — same rationale as the other *Service classes
    (architecture doc Section 14). The worker-side PDF generation pipeline lives in
    ReportGenerationService instead, which is never called from here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._reports = ReportRepository(session)
        self._shipments = ShipmentRepository(session)
        self._storage = ObjectStorageClient()
        self._settings = get_settings()

    async def trigger_generation(
        self, shipment_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> Report:
        shipment = await self._shipments.get_by_id_scoped(shipment_id, accessible_company_ids)
        if shipment is None:
            raise NotFoundError("Shipment not found.")

        report = await self._reports.create(
            Report(shipment_id=shipment_id, status=ReportStatus.GENERATING)
        )
        # Commit before enqueueing — same rationale as document_service.py's
        # upload_document (the worker reads from its own connection).
        await self._session.commit()
        celery_app.send_task("generate_report", args=[str(report.id)])
        return report

    async def get_report(
        self, report_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> tuple[Report, str | None]:
        report = await self._reports.get_by_id_scoped(report_id, accessible_company_ids)
        if report is None:
            raise NotFoundError("Report not found.")

        download_url = None
        if report.status == ReportStatus.READY and report.storage_path:
            download_url = self._storage.generate_presigned_url(
                report.storage_path,
                expires_in_seconds=self._settings.report_download_url_expire_seconds,
            )
        return report, download_url
