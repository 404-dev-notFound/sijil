import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.object_storage import ObjectStorageClient
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType, ShipmentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.services.shipment_status_transitions import compute_shipment_status
from app.utils.exceptions import ConflictError, NotFoundError, UnprocessableError, ValidationError
from app.utils.file_validation import MAX_FILE_SIZE_BYTES, sniff_content_type
from app.workers.celery_app import celery_app


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._shipments = ShipmentRepository(session)
        self._documents = DocumentRepository(session)
        self._storage = ObjectStorageClient()

    async def upload_document(
        self,
        *,
        shipment_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
        doc_type: DocumentType,
        filename: str,
        file_bytes: bytes,
    ) -> Document:
        shipment = await self._shipments.get_by_id_scoped(shipment_id, accessible_company_ids)
        if shipment is None:
            raise NotFoundError("Shipment not found.")

        if len(file_bytes) == 0:
            raise ValidationError("Uploaded file is empty.")
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                "File exceeds the 20MB size limit.", details={"field": "file"}
            )

        detected_content_type = sniff_content_type(file_bytes[:16])
        if detected_content_type is None:
            # Surfaced immediately, before queueing — architecture doc Section 31 edge
            # case ("Corrupt/unreadable uploaded file").
            raise UnprocessableError(
                "File content doesn't match a supported type (PDF, JPEG, or PNG). "
                "The file may be corrupt or an unsupported format."
            )

        document_id = uuid.uuid4()
        storage_key = self._storage.build_document_key(
            company_id=shipment.company_id,
            shipment_id=shipment.id,
            document_id=document_id,
            filename=filename,
        )
        self._storage.upload(
            key=storage_key, body=file_bytes, content_type=detected_content_type
        )

        document = await self._documents.create(
            Document(
                id=document_id,
                shipment_id=shipment.id,
                doc_type=doc_type,
                status=DocumentStatus.QUEUED,
                storage_path=storage_key,
                original_filename=filename,
                content_type=detected_content_type,
                size_bytes=len(file_bytes),
            )
        )

        if shipment.status == ShipmentStatus.CREATED:
            shipment.status = ShipmentStatus.DOCUMENTS_UPLOADING

        # Commit before enqueueing: the worker runs in a separate process against its
        # own DB connection, so it must never be able to dequeue and look up a document
        # row that isn't durably committed yet (get_db's usual "commit after the route
        # handler returns" would otherwise race the worker).
        await self._session.commit()
        celery_app.send_task("process_document", args=[str(document.id)])

        return document

    async def get_document(
        self,
        *,
        shipment_id: uuid.UUID,
        document_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
    ) -> Document:
        document = await self._documents.get_by_id_scoped(document_id, accessible_company_ids)
        if document is None or document.shipment_id != shipment_id:
            raise NotFoundError("Document not found.")
        return document

    async def correct_extracted_fields(
        self,
        *,
        shipment_id: uuid.UUID,
        document_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
        corrected_fields: dict[str, Any],
    ) -> Document:
        document = await self._documents.get_by_id_scoped(document_id, accessible_company_ids)
        if document is None or document.shipment_id != shipment_id:
            raise NotFoundError("Document not found.")
        if document.status != DocumentStatus.NEEDS_MANUAL_REVIEW:
            raise ConflictError(
                "Only documents with status needs_manual_review can be manually corrected.",
                details={"status": document.status},
            )

        document.extracted_fields = {**(document.extracted_fields or {}), **corrected_fields}
        document.status = DocumentStatus.EXTRACTED

        sibling_documents = await self._documents.list_by_shipment_scoped(
            shipment_id, accessible_company_ids
        )
        new_status = compute_shipment_status(sibling_documents)
        if new_status is not None:
            shipment = await self._shipments.get_by_id_scoped(
                shipment_id, accessible_company_ids
            )
            if shipment is not None:
                shipment.status = new_status

        should_classify = document.doc_type == DocumentType.COMMERCIAL_INVOICE
        # Commit before enqueueing — same rationale as upload_document above.
        await self._session.commit()
        if should_classify:
            celery_app.send_task(
                "classify_shipment_from_document", args=[str(document.id)]
            )

        return document
