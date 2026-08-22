from app.models.document import Document
from app.models.enums import DocumentStatus, ShipmentStatus

_IN_PROGRESS = (DocumentStatus.QUEUED, DocumentStatus.PROCESSING)


def compute_shipment_status(documents: list[Document]) -> ShipmentStatus | None:
    """Derives a shipment's status from its documents' statuses — a pure function
    (no repository access of its own) shared by the extraction worker
    (app/services/document_extraction_service.py, unscoped document fetch) and the
    manual-correction endpoint (app/services/document_service.py, tenant-scoped
    document fetch), so a document changing status always moves the owning shipment
    the same way regardless of which path triggered it. Deliberately takes an
    already-fetched document list rather than a shipment_id + repository, so each
    caller stays responsible for fetching those documents through whichever
    scoped/unscoped method is correct for its own context (architecture doc Section 14)
    — this function can't accidentally bypass tenant scoping because it never queries
    anything itself.

    Returns None if there are no documents yet (nothing to derive from).
    """
    if not documents:
        return None
    if any(document.status in _IN_PROGRESS for document in documents):
        return ShipmentStatus.EXTRACTING
    if any(document.status == DocumentStatus.NEEDS_MANUAL_REVIEW for document in documents):
        return ShipmentStatus.NEEDS_MANUAL_REVIEW
    # All documents extracted — awaiting Phase 3 classification, not yet wired up.
    return ShipmentStatus.EXTRACTING
