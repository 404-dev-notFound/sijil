from enum import StrEnum


class AccountType(StrEnum):
    TRADING_COMPANY = "trading_company"
    BROKER = "broker"


class UserRole(StrEnum):
    COMPANY_ADMIN = "company_admin"
    COMPANY_USER = "company_user"
    BROKER_ADMIN = "broker_admin"
    BROKER_USER = "broker_user"


class ShipmentDirection(StrEnum):
    IMPORT = "import"
    EXPORT = "export"


class ShipmentStatus(StrEnum):
    """Mirrors the state machine in architecture doc Section 30. Only the first two
    transitions (CREATED -> DOCUMENTS_UPLOADING) are reachable in Phase 1 — the rest
    are wired up as extraction/classification/etc. land in later phases."""

    CREATED = "created"
    DOCUMENTS_UPLOADING = "documents_uploading"
    EXTRACTING = "extracting"
    CLASSIFYING = "classifying"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    ANALYSIS_COMPLETE = "analysis_complete"
    REPORT_GENERATED = "report_generated"


class DocumentType(StrEnum):
    COMMERCIAL_INVOICE = "commercial_invoice"
    PACKING_LIST = "packing_list"
    BILL_OF_LADING = "bill_of_lading"
    AIR_WAYBILL = "air_waybill"


class DocumentStatus(StrEnum):
    """Phase 1 only ever produces QUEUED (upload storage, no processing yet).
    EXTRACTED/NEEDS_MANUAL_REVIEW/FAILED are reachable starting Phase 2."""

    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    FAILED = "failed"


class DiscrepancySeverity(StrEnum):
    """architecture doc Section 2.3 / API SPEC Section 9. A shipment cannot move to
    analysis_complete while a BLOCKING discrepancy is unresolved — not yet enforced
    anywhere, since nothing transitions a shipment to analysis_complete until Phase
    5/6 exist; whichever phase adds that transition must check for unresolved
    BLOCKING discrepancies first."""

    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATIONAL = "informational"
