from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf
from tests.integration.helpers import (
    auth_headers,
    register_company,
    wait_for_line_items_classified,
)


async def _upload_invoice(
    client: AsyncClient, *, shipment_id: str, headers: dict[str, str], lines: list[str]
) -> None:
    pdf_bytes = build_text_pdf([lines])
    response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": "commercial_invoice"},
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 202, response.text


async def _new_shipment(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/shipments", json={"direction": "import"}, headers=headers
    )
    assert response.status_code == 201, response.text
    shipment_id: str = response.json()["id"]
    return shipment_id


async def test_invoice_line_items_are_classified_end_to_end(client: AsyncClient) -> None:
    """The Phase 3 definition of done, exercised through the real pipeline: an
    invoice's line items are extracted (Phase 2), materialized as LineItem rows, and
    classified with visible confidence and reasoning — never a silent, confidence-less
    result."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-300001", email="cls1@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-3000-01",
            "Seller: Test Seller Co",
            "Buyer: Test Buyer LLC",
            "Total Value: 5000.00 USD",
            "Line Item: 24-port managed network switch for a data center | Qty: 2 | "
            "Unit Value: 185.00 USD",
            "Line Item: 13-inch laptop computer, 1.1kg, aluminum body | Qty: 5 | "
            "Unit Value: 900.00 USD",
        ],
    )

    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=2
    )
    assert len(items) == 2
    descriptions = {item["description"] for item in items}
    assert "24-port managed network switch for a data center" in descriptions
    assert "13-inch laptop computer, 1.1kg, aluminum body" in descriptions

    for item in items:
        classification = item["classification"]
        assert classification["top_candidate"]["hs_code"] is not None
        assert 0.0 <= classification["top_candidate"]["confidence"] <= 1.0
        assert classification["top_candidate"]["reasoning"]
        assert classification["user_override_hs_code"] is None


async def test_novel_product_with_no_good_match_needs_manual_review(
    client: AsyncClient,
) -> None:
    """A product with no strong match in the (small, illustrative) tariff knowledge
    base correctly surfaces low confidence rather than a false-confident guess
    (architecture doc's "Do Not Do This" rules)."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-300002", email="cls2@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-3000-02",
            "Seller: Test Seller Co",
            "Buyer: Test Buyer LLC",
            "Total Value: 100.00 USD",
            "Line Item: Experimental quantum entanglement communicator prototype | "
            "Qty: 1 | Unit Value: 100.00 USD",
        ],
    )

    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    classification = items[0]["classification"]
    assert classification["requires_manual_review"] is True


async def test_override_classification_retains_ai_suggestion(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-300003", email="cls3@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-3000-03",
            "Seller: Test Seller Co",
            "Buyer: Test Buyer LLC",
            "Total Value: 900.00 USD",
            "Line Item: 13-inch laptop computer, 1.1kg, aluminum body | Qty: 1 | "
            "Unit Value: 900.00 USD",
        ],
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    line_item_id = items[0]["id"]
    original_hs_code = items[0]["classification"]["top_candidate"]["hs_code"]

    override_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/line-items/{line_item_id}/override",
        json={"hs_code": "9999.99.99.99", "reason": "Confirmed with our customs broker"},
        headers=headers,
    )
    assert override_response.status_code == 200, override_response.text
    body = override_response.json()
    assert body["classification"]["user_override_hs_code"] == "9999.99.99.99"
    # The AI's original suggestion is retained, never overwritten by the override.
    assert body["classification"]["top_candidate"]["hs_code"] == original_hs_code


async def test_reclassify_triggers_a_fresh_classification(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-300004", email="cls4@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-3000-04",
            "Seller: Test Seller Co",
            "Buyer: Test Buyer LLC",
            "Total Value: 185.00 USD",
            "Line Item: 24-port managed network switch for a data center | Qty: 1 | "
            "Unit Value: 185.00 USD",
        ],
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    line_item_id = items[0]["id"]

    reclassify_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/line-items/{line_item_id}/reclassify",
        headers=headers,
    )
    assert reclassify_response.status_code == 202, reclassify_response.text
    assert reclassify_response.json()["status"] == "processing"

    refreshed = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    assert refreshed[0]["classification"]["top_candidate"]["hs_code"] is not None


async def test_company_a_cannot_read_company_bs_line_items(client: AsyncClient) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-300005", email="cls5a@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-300006", email="cls5b@example.com"
    )
    headers_b = auth_headers(token_b)
    shipment_b = await _new_shipment(client, headers_b)
    await _upload_invoice(
        client,
        shipment_id=shipment_b,
        headers=headers_b,
        lines=[
            "Invoice Number: INV-3000-05",
            "Seller: Test Seller Co",
            "Buyer: Test Buyer LLC",
            "Total Value: 900.00 USD",
            "Line Item: 13-inch laptop computer, 1.1kg, aluminum body | Qty: 1 | "
            "Unit Value: 900.00 USD",
        ],
    )
    await wait_for_line_items_classified(
        client, shipment_id=shipment_b, headers=headers_b, expected_count=1
    )

    headers_a = auth_headers(token_a)
    response = await client.get(
        f"/api/v1/shipments/{shipment_b}/line-items", headers=headers_a
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
