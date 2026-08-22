import uuid
from datetime import UTC, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.object_storage import ObjectStorageClient
from app.models.discrepancy import Discrepancy
from app.models.enums import ReportStatus
from app.models.line_item import LineItem
from app.models.permit_requirement import PermitRequirement
from app.models.shipment import Shipment
from app.repositories.discrepancy_repository import DiscrepancyRepository
from app.repositories.line_item_repository import LineItemRepository
from app.repositories.permit_requirement_repository import PermitRequirementRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.shipment_repository import ShipmentRepository

_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]
)


class ReportGenerationService:
    """Bundles classification, discrepancies, permits, and origin results for one
    shipment into a downloadable PDF (architecture doc Section 9 / API SPEC Section
    12) — the report is an advisory summary of Sijil's current analysis, not a filing
    document (CLAUDE.md: Sijil never auto-files anything with a government system).
    Worker-only, same rationale as the other generation services (architecture doc
    Section 14).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._reports = ReportRepository(session)
        self._shipments = ShipmentRepository(session)
        self._line_items = LineItemRepository(session)
        self._discrepancies = DiscrepancyRepository(session)
        self._permits = PermitRequirementRepository(session)
        self._storage = ObjectStorageClient()

    async def generate(self, report_id: uuid.UUID) -> None:
        report = await self._reports.get_by_id(report_id)
        if report is None:
            return

        shipment = await self._shipments.get_by_id(report.shipment_id)
        if shipment is None:
            report.status = ReportStatus.FAILED
            return

        try:
            line_items = await self._line_items.list_by_shipment(shipment.id)
            discrepancies = await self._discrepancies.list_by_shipment(shipment.id)
            permits = await self._permits.list_by_shipment(shipment.id)
            pdf_bytes = _build_pdf(
                shipment=shipment,
                line_items=line_items,
                discrepancies=discrepancies,
                permits=permits,
            )
            storage_key = ObjectStorageClient.build_report_key(
                company_id=shipment.company_id, shipment_id=shipment.id, report_id=report.id
            )
            self._storage.upload(key=storage_key, body=pdf_bytes, content_type="application/pdf")
        except Exception:
            report.status = ReportStatus.FAILED
            return

        report.status = ReportStatus.READY
        report.storage_path = storage_key
        report.generated_at = datetime.now(UTC)


def _build_pdf(
    *,
    shipment: Shipment,
    line_items: list[LineItem],
    discrepancies: list[Discrepancy],
    permits: list[PermitRequirement],
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Sijil Compliance Report")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Sijil Compliance Report", styles["Title"]),
        Paragraph(
            f"Shipment {shipment.id} &middot; {shipment.direction.value} &middot; "
            f"status: {shipment.status.value}",
            styles["Normal"],
        ),
        Paragraph(
            "Advisory only — Sijil does not file with Dubai Customs or any other "
            "government system. Review and file this shipment yourself.",
            styles["Italic"],
        ),
        Spacer(1, 0.25 * inch),
    ]

    story.append(Paragraph("HS Classification", styles["Heading2"]))
    if line_items:
        rows = [["Description", "HS Code", "Confidence", "Manual Review"]]
        for item in line_items:
            classification = item.classification
            rows.append(
                [
                    item.description,
                    (classification.user_override_hs_code or classification.hs_code or "—")
                    if classification
                    else "—",
                    f"{classification.confidence:.0%}" if classification else "—",
                    "Yes" if classification and classification.requires_manual_review else "No",
                ]
            )
        story.append(Table(rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No line items extracted yet.", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Consistency Discrepancies", styles["Heading2"]))
    if discrepancies:
        rows = [["Field", "Severity", "Description"]]
        for discrepancy in discrepancies:
            rows.append([discrepancy.field, discrepancy.severity.value, discrepancy.description])
        story.append(Table(rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No discrepancies found.", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Permit Requirements", styles["Heading2"]))
    if permits:
        rows = [["Regulator", "Permit Type", "Est. Processing (days)"]]
        for permit in permits:
            rows.append(
                [permit.regulator, permit.permit_type, str(permit.estimated_processing_time_days)]
            )
        story.append(Table(rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No permits required.", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("CEPA Origin Determination", styles["Heading2"]))
    origin_rows = [["Line Item", "Agreement", "Status", "Est. Savings"]]
    has_origin = False
    for item in line_items:
        determination = item.origin_determination
        if determination is None:
            continue
        has_origin = True
        savings = (
            f"{determination.estimated_duty_savings_amount} "
            f"{determination.estimated_duty_savings_currency}"
            if determination.estimated_duty_savings_amount is not None
            else "—"
        )
        origin_rows.append(
            [
                item.description,
                determination.agreement or "—",
                determination.qualifies.value,
                savings,
            ]
        )
    if has_origin:
        story.append(Table(origin_rows, style=_TABLE_STYLE, hAlign="LEFT"))
    else:
        story.append(Paragraph("No CEPA origin determinations yet.", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
