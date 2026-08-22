from typing import Any

from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType
from app.services.consistency_service import _compare_name_field, _compare_quantity


def _document(
    doc_type: DocumentType,
    fields: dict[str, Any],
    *,
    status: DocumentStatus = DocumentStatus.EXTRACTED,
) -> Document:
    return Document(
        doc_type=doc_type,
        status=status,
        storage_path="irrelevant",
        original_filename="irrelevant.pdf",
        content_type="application/pdf",
        size_bytes=1,
        extracted_fields=fields,
    )


def test_quantity_mismatch_is_blocking() -> None:
    """The Phase 4 definition of done: a deliberately introduced invoice/packing-list
    quantity mismatch is correctly flagged as blocking."""
    invoice = _document(
        DocumentType.COMMERCIAL_INVOICE,
        {"line_items": [{"quantity": "10"}]},
    )
    packing_list = _document(DocumentType.PACKING_LIST, {"total_packages": "12"})

    candidates = _compare_quantity({invoice.doc_type: invoice, packing_list.doc_type: packing_list})

    assert len(candidates) == 1
    assert candidates[0].field == "quantity"
    assert candidates[0].severity == "blocking"
    assert "10" in candidates[0].description
    assert "12" in candidates[0].description


def test_quantity_match_yields_no_discrepancy() -> None:
    invoice = _document(
        DocumentType.COMMERCIAL_INVOICE,
        {"line_items": [{"quantity": "5"}, {"quantity": "5"}]},
    )
    packing_list = _document(DocumentType.PACKING_LIST, {"total_packages": "10"})

    candidates = _compare_quantity({invoice.doc_type: invoice, packing_list.doc_type: packing_list})

    assert candidates == []


def test_quantity_missing_field_is_warning_not_blocking() -> None:
    invoice = _document(DocumentType.COMMERCIAL_INVOICE, {"line_items": []})
    packing_list = _document(DocumentType.PACKING_LIST, {"total_packages": "10"})

    candidates = _compare_quantity({invoice.doc_type: invoice, packing_list.doc_type: packing_list})

    assert len(candidates) == 1
    assert candidates[0].severity == "warning"


def test_quantity_missing_document_yields_no_discrepancy() -> None:
    invoice = _document(
        DocumentType.COMMERCIAL_INVOICE, {"line_items": [{"quantity": "10"}]}
    )

    candidates = _compare_quantity({invoice.doc_type: invoice})

    assert candidates == []


def test_minor_name_formatting_difference_is_non_blocking() -> None:
    """The Phase 4 definition of done: a shipment with only minor name-formatting
    differences ("LLC" vs "L.L.C.") is correctly treated as non-blocking — in this
    scaffold, similar enough that it isn't flagged as a discrepancy at all."""
    invoice = _document(
        DocumentType.COMMERCIAL_INVOICE, {"buyer": "Al Falah Trading LLC"}
    )
    bol = _document(DocumentType.BILL_OF_LADING, {"consignee": "Al Falah Trading L.L.C."})

    candidates = _compare_name_field(
        {invoice.doc_type: invoice, bol.doc_type: bol},
        invoice_field="buyer",
        target_field="consignee",
        result_field="buyer_consignee_name",
    )

    assert candidates == []


def test_substantially_different_name_is_a_warning_never_blocking() -> None:
    invoice = _document(DocumentType.COMMERCIAL_INVOICE, {"seller": "Shenzhen Tech Co Ltd"})
    bol = _document(DocumentType.BILL_OF_LADING, {"shipper": "Globex Industries FZE"})

    candidates = _compare_name_field(
        {invoice.doc_type: invoice, bol.doc_type: bol},
        invoice_field="seller",
        target_field="shipper",
        result_field="seller_shipper_name",
    )

    assert len(candidates) == 1
    assert candidates[0].severity == "warning"


def test_name_field_missing_on_one_document_is_a_warning() -> None:
    invoice = _document(DocumentType.COMMERCIAL_INVOICE, {"seller": None})
    bol = _document(DocumentType.BILL_OF_LADING, {"shipper": "Globex Industries FZE"})

    candidates = _compare_name_field(
        {invoice.doc_type: invoice, bol.doc_type: bol},
        invoice_field="seller",
        target_field="shipper",
        result_field="seller_shipper_name",
    )

    assert len(candidates) == 1
    assert candidates[0].severity == "warning"


def test_name_field_no_target_document_yields_no_discrepancy() -> None:
    invoice = _document(DocumentType.COMMERCIAL_INVOICE, {"seller": "Shenzhen Tech Co Ltd"})

    candidates = _compare_name_field(
        {invoice.doc_type: invoice},
        invoice_field="seller",
        target_field="shipper",
        result_field="seller_shipper_name",
    )

    assert candidates == []
