from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType, ShipmentStatus
from app.services.shipment_status_transitions import compute_shipment_status


def _document(status: DocumentStatus) -> Document:
    return Document(
        doc_type=DocumentType.COMMERCIAL_INVOICE,
        status=status,
        storage_path="irrelevant",
        original_filename="irrelevant.pdf",
        content_type="application/pdf",
        size_bytes=1,
    )


def test_returns_none_for_no_documents() -> None:
    assert compute_shipment_status([]) is None


def test_any_document_in_progress_yields_extracting() -> None:
    documents = [_document(DocumentStatus.QUEUED), _document(DocumentStatus.EXTRACTED)]

    assert compute_shipment_status(documents) == ShipmentStatus.EXTRACTING


def test_any_document_needing_review_yields_needs_manual_review() -> None:
    documents = [
        _document(DocumentStatus.EXTRACTED),
        _document(DocumentStatus.NEEDS_MANUAL_REVIEW),
    ]

    assert compute_shipment_status(documents) == ShipmentStatus.NEEDS_MANUAL_REVIEW


def test_in_progress_takes_priority_over_needs_review() -> None:
    documents = [
        _document(DocumentStatus.PROCESSING),
        _document(DocumentStatus.NEEDS_MANUAL_REVIEW),
    ]

    assert compute_shipment_status(documents) == ShipmentStatus.EXTRACTING


def test_all_extracted_yields_extracting_pending_phase_3() -> None:
    documents = [_document(DocumentStatus.EXTRACTED), _document(DocumentStatus.EXTRACTED)]

    assert compute_shipment_status(documents) == ShipmentStatus.EXTRACTING
