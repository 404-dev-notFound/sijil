import uuid
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discrepancy import Discrepancy
from app.models.document import Document
from app.models.enums import DiscrepancySeverity, DocumentStatus, DocumentType
from app.repositories.discrepancy_repository import DiscrepancyRepository
from app.repositories.document_repository import DocumentRepository
from app.utils.decimals import parse_decimal

# Below this Ratcliff/Obershelp similarity ratio (difflib.SequenceMatcher), a name
# pair is flagged for human review — legal-suffix/formatting differences ("LLC" vs
# "L.L.C.") score well above this; a genuinely different company name does not.
_NAME_WARNING_THRESHOLD = 0.6

_NAME_TARGET_DOC_TYPES = (DocumentType.BILL_OF_LADING, DocumentType.AIR_WAYBILL)


@dataclass
class _Candidate:
    field: str
    severity: DiscrepancySeverity
    documents_involved: list[str]
    description: str
    suggested_resolution: str


class ConsistencyService:
    """Field-by-field comparison across a shipment's extracted documents (architecture
    doc Section 6.2): exact match for quantities, fuzzy match for names/addresses. A
    missing field on an otherwise-present document is a warning, never a blocking
    error — some fields legitimately don't appear on every document type. Worker-only,
    same rationale as DocumentExtractionService/ClassificationService (architecture
    doc Section 14).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._documents = DocumentRepository(session)
        self._discrepancies = DiscrepancyRepository(session)

    async def check_shipment(self, shipment_id: uuid.UUID) -> None:
        documents = await self._documents.list_by_shipment(shipment_id)
        by_type = {
            document.doc_type: document
            for document in documents
            if document.status in (DocumentStatus.EXTRACTED, DocumentStatus.NEEDS_MANUAL_REVIEW)
        }

        candidates = _compare_quantity(by_type)
        candidates += _compare_name_field(
            by_type,
            invoice_field="seller",
            target_field="shipper",
            result_field="seller_shipper_name",
        )
        candidates += _compare_name_field(
            by_type,
            invoice_field="buyer",
            target_field="consignee",
            result_field="buyer_consignee_name",
        )

        await self._reconcile(shipment_id, candidates)

    async def _reconcile(self, shipment_id: uuid.UUID, candidates: list[_Candidate]) -> None:
        existing_by_field = {
            discrepancy.field: discrepancy
            for discrepancy in await self._discrepancies.list_by_shipment(shipment_id)
        }
        seen_fields: set[str] = set()

        for candidate in candidates:
            seen_fields.add(candidate.field)
            row = existing_by_field.get(candidate.field)
            if row is None:
                await self._discrepancies.create(
                    Discrepancy(
                        shipment_id=shipment_id,
                        field=candidate.field,
                        severity=candidate.severity,
                        documents_involved=candidate.documents_involved,
                        description=candidate.description,
                        suggested_resolution=candidate.suggested_resolution,
                    )
                )
            else:
                # acknowledged / acknowledged_by_user_id / acknowledged_at are
                # deliberately left untouched — re-evaluating the same field on a
                # later run must never silently clear a user's acknowledgment.
                row.severity = candidate.severity
                row.documents_involved = candidate.documents_involved
                row.description = candidate.description
                row.suggested_resolution = candidate.suggested_resolution

        for field, row in existing_by_field.items():
            if field not in seen_fields:
                # No longer applicable (e.g. a corrected document now matches) —
                # removed rather than left stale.
                await self._discrepancies.delete(row)


def _compare_quantity(by_type: dict[DocumentType, Document]) -> list[_Candidate]:
    invoice = by_type.get(DocumentType.COMMERCIAL_INVOICE)
    packing_list = by_type.get(DocumentType.PACKING_LIST)
    if invoice is None or packing_list is None:
        return []

    invoice_qty = _sum_line_item_quantities(invoice.extracted_fields or {})
    packing_qty = parse_decimal((packing_list.extracted_fields or {}).get("total_packages"))
    documents_involved = [str(invoice.id), str(packing_list.id)]

    if invoice_qty is None or packing_qty is None:
        missing_doc = invoice if invoice_qty is None else packing_list
        return [
            _Candidate(
                field="quantity",
                severity=DiscrepancySeverity.WARNING,
                documents_involved=documents_involved,
                description=(
                    f"Quantity field missing or unreadable on the {missing_doc.doc_type.value} "
                    "— cannot verify consistency."
                ),
                suggested_resolution=(
                    "Ensure both the commercial invoice and packing list clearly state quantities."
                ),
            )
        ]

    if invoice_qty != packing_qty:
        return [
            _Candidate(
                field="quantity",
                severity=DiscrepancySeverity.BLOCKING,
                documents_involved=documents_involved,
                description=(
                    f"Commercial invoice states {invoice_qty} units; packing list states "
                    f"{packing_qty} units."
                ),
                suggested_resolution=(
                    "Confirm actual shipped quantity with your supplier and correct whichever "
                    "document is wrong before filing."
                ),
            )
        ]
    return []


def _compare_name_field(
    by_type: dict[DocumentType, Document],
    *,
    invoice_field: str,
    target_field: str,
    result_field: str,
) -> list[_Candidate]:
    invoice = by_type.get(DocumentType.COMMERCIAL_INVOICE)
    if invoice is None:
        return []

    # A shipment realistically has a bill of lading (sea) or an air waybill (air), not
    # both — compare against whichever transport document is present.
    target = next(
        (by_type[doc_type] for doc_type in _NAME_TARGET_DOC_TYPES if doc_type in by_type), None
    )
    if target is None:
        return []

    invoice_name = (invoice.extracted_fields or {}).get(invoice_field)
    target_name = (target.extracted_fields or {}).get(target_field)
    documents_involved = [str(invoice.id), str(target.id)]

    if not invoice_name or not target_name:
        missing_doc = invoice if not invoice_name else target
        missing_field = invoice_field if not invoice_name else target_field
        return [
            _Candidate(
                field=result_field,
                severity=DiscrepancySeverity.WARNING,
                documents_involved=documents_involved,
                description=(
                    f"{missing_field.capitalize()} field missing on the "
                    f"{missing_doc.doc_type.value} — cannot verify consistency."
                ),
                suggested_resolution=(
                    f"Ensure both documents clearly state the {invoice_field}/{target_field}."
                ),
            )
        ]

    similarity = SequenceMatcher(
        None, invoice_name.strip().lower(), target_name.strip().lower()
    ).ratio()
    if similarity < _NAME_WARNING_THRESHOLD:
        return [
            _Candidate(
                field=result_field,
                severity=DiscrepancySeverity.WARNING,
                documents_involved=documents_involved,
                description=(
                    f'Commercial invoice {invoice_field} "{invoice_name}" does not closely match '
                    f'{target.doc_type.value} {target_field} "{target_name}".'
                ),
                suggested_resolution=(
                    "Confirm the correct company name and spelling across all shipment documents."
                ),
            )
        ]
    return []


def _sum_line_item_quantities(fields: dict[str, object]) -> Decimal | None:
    line_items = fields.get("line_items")
    if not isinstance(line_items, list) or not line_items:
        return None

    total = Decimal("0")
    found_any = False
    for item in line_items:
        if not isinstance(item, dict):
            continue
        quantity = parse_decimal(item.get("quantity"))
        if quantity is not None:
            total += quantity
            found_any = True
    return total if found_any else None
