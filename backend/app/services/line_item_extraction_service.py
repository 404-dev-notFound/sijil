import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DocumentType
from app.models.line_item import LineItem
from app.repositories.document_repository import DocumentRepository
from app.repositories.line_item_repository import LineItemRepository
from app.utils.decimals import parse_decimal


class LineItemExtractionService:
    """Turns a commercial invoice document's extracted_fields.line_items (Phase 2
    output) into LineItem rows ClassificationService can classify. Worker-only —
    operates on a document_id by internal system trust, same rationale as
    DocumentExtractionService (architecture doc Section 14).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._documents = DocumentRepository(session)
        self._line_items = LineItemRepository(session)

    async def materialize_from_document(self, document_id: uuid.UUID) -> list[LineItem]:
        document = await self._documents.get_by_id(document_id)
        if document is None or document.doc_type != DocumentType.COMMERCIAL_INVOICE:
            return []

        raw_items = (document.extracted_fields or {}).get("line_items", [])
        line_items = [
            self._to_line_item(document.shipment_id, raw_item) for raw_item in raw_items
        ]
        return await self._line_items.replace_for_shipment(document.shipment_id, line_items)

    def _to_line_item(self, shipment_id: uuid.UUID, raw: dict[str, Any]) -> LineItem:
        unit_value = raw.get("unit_value") or {}
        return LineItem(
            shipment_id=shipment_id,
            description=raw.get("description") or "",
            quantity=parse_decimal(raw.get("quantity")),
            unit_value=parse_decimal(unit_value.get("amount")),
            currency=unit_value.get("currency"),
        )
