from app.integrations.llm_client import MockLLMClient


def test_extract_document_fields_returns_zero_confidence_for_empty_text() -> None:
    result = MockLLMClient().extract_document_fields("", "commercial_invoice")

    assert result == {"fields": {}, "confidence": 0.0}


def test_extract_document_fields_parses_all_expected_invoice_fields() -> None:
    raw_text = (
        "Invoice Number: INV-2026-0451\n"
        "Seller: Shenzhen Tech Co Ltd\n"
        "Buyer: Al Falah Trading LLC\n"
        "Total Value: 18500.00 USD\n"
    )

    result = MockLLMClient().extract_document_fields(raw_text, "commercial_invoice")

    assert result["confidence"] == 1.0
    assert result["fields"]["invoice_number"] == "INV-2026-0451"
    assert result["fields"]["total_value"] == {"amount": "18500.00", "currency": "USD"}


def test_extract_document_fields_partial_match_yields_partial_confidence() -> None:
    raw_text = "Invoice Number: INV-2026-0001\n"

    result = MockLLMClient().extract_document_fields(raw_text, "commercial_invoice")

    assert result["confidence"] == 0.25
    assert result["fields"] == {"invoice_number": "INV-2026-0001"}


def test_extract_document_fields_unknown_doc_type_yields_zero_confidence() -> None:
    result = MockLLMClient().extract_document_fields(
        "Some Field: some value\n", "unknown_doc_type"
    )

    assert result["confidence"] == 0.0
