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


def test_extract_document_fields_parses_line_items_without_affecting_confidence() -> None:
    raw_text = (
        "Invoice Number: INV-2026-0451\n"
        "Seller: Shenzhen Tech Co Ltd\n"
        "Buyer: Al Falah Trading LLC\n"
        "Total Value: 18500.00 USD\n"
        "Line Item: 24-port managed network switch | Qty: 10 | Unit Value: 185.00 USD\n"
    )

    result = MockLLMClient().extract_document_fields(raw_text, "commercial_invoice")

    # line_items isn't one of the 4 expected top-level fields, so confidence still
    # reflects only invoice_number/seller/buyer/total_value — adding line items must
    # never silently change what confidence means for already-shipped fixtures.
    assert result["confidence"] == 1.0
    assert result["fields"]["line_items"] == [
        {
            "description": "24-port managed network switch",
            "quantity": "10",
            "unit_value": {"amount": "185.00", "currency": "USD"},
        }
    ]


def test_classify_product_returns_low_confidence_with_no_candidates() -> None:
    result = MockLLMClient().classify_product("some product", [])

    assert result["hs_code"] is None
    assert result["confidence"] == 0.0
    assert result["alternatives"] == []


def test_classify_product_picks_nearest_candidate_by_distance() -> None:
    candidates = [
        {"hs_code": "8471.30", "description": "laptops", "distance": 0.1},
        {"hs_code": "8517.62", "description": "network switches", "distance": 0.4},
    ]

    result = MockLLMClient().classify_product("13-inch laptop", candidates)

    assert result["hs_code"] == "8471.30"
    assert result["confidence"] == 0.9
    assert result["alternatives"] == [{"hs_code": "8517.62", "confidence": 0.6}]


def test_classify_product_clamps_confidence_to_valid_range() -> None:
    candidates = [{"hs_code": "9999.99", "description": "unrelated", "distance": 1.7}]

    result = MockLLMClient().classify_product("something", candidates)

    assert result["confidence"] == 0.0
