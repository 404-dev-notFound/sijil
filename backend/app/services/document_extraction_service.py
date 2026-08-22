import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.integrations.llm_client import LLMClient, get_llm_client
from app.integrations.object_storage import ObjectStorageClient
from app.integrations.ocr_client import OCRClient, get_ocr_client
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.services.shipment_status_transitions import compute_shipment_status
from app.utils.pdf_text import MIN_NATIVE_TEXT_CHARS, extract_native_pdf_text

logger = logging.getLogger(__name__)


class DocumentExtractionService:
    """OCR -> LLM field extraction for one document (architecture doc Section 11.1).
    Called only from the background worker (app/workers/document_processing_tasks.py)
    — never from an API route, since it operates on a document_id by internal system
    trust rather than a tenant-scoped user request.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        llm_client: LLMClient | None = None,
        ocr_client: OCRClient | None = None,
    ) -> None:
        self._session = session
        self._documents = DocumentRepository(session)
        self._shipments = ShipmentRepository(session)
        self._storage = ObjectStorageClient()
        self._llm = llm_client or get_llm_client()
        self._ocr = ocr_client or get_ocr_client()
        self._settings = get_settings()

    async def extract(self, document_id: uuid.UUID) -> Document | None:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            # Idempotency: re-running for a document that no longer exists is a no-op,
            # not an error (architecture doc Section 12).
            return None

        document.status = DocumentStatus.PROCESSING
        await self._recompute_shipment_status(document.shipment_id)
        await self._session.flush()

        try:
            file_bytes = self._storage.download(document.storage_path)
            raw_text = self._extract_raw_text(file_bytes, document.content_type)
            result = self._llm.extract_document_fields(raw_text, document.doc_type)
            fields = result.get("fields", {})
            confidence = float(result.get("confidence", 0.0))
        except Exception:
            logger.exception("Document extraction failed for document_id=%s", document_id)
            fields, confidence = {}, 0.0

        document.extracted_fields = fields
        document.extraction_confidence = confidence
        document.status = (
            DocumentStatus.EXTRACTED
            if confidence >= self._settings.extraction_confidence_threshold
            else DocumentStatus.NEEDS_MANUAL_REVIEW
        )
        await self._recompute_shipment_status(document.shipment_id)
        return document

    def _extract_raw_text(self, file_bytes: bytes, content_type: str) -> str:
        if content_type == "application/pdf":
            native_text = extract_native_pdf_text(file_bytes)
            if len(native_text.strip()) >= MIN_NATIVE_TEXT_CHARS:
                return native_text
        return self._ocr.extract_text(file_bytes, content_type)

    async def _recompute_shipment_status(self, shipment_id: uuid.UUID) -> None:
        # Unscoped fetches — safe only because this whole service is worker-only,
        # never reachable from an API route (architecture doc Section 14).
        documents = await self._documents.list_by_shipment(shipment_id)
        new_status = compute_shipment_status(documents)
        if new_status is None:
            return
        shipment = await self._shipments.get_by_id(shipment_id)
        if shipment is not None:
            shipment.status = new_status
