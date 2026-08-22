from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf
from tests.integration.helpers import (
    auth_headers,
    register_company,
    wait_for_document_status,
    wait_for_line_items_classified,
    wait_for_permits,
    wait_for_permits_settled,
)

_TERMINAL_DOC_STATUSES = {"extracted", "needs_manual_review"}


async def _new_shipment(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/shipments", json={"direction": "import"}, headers=headers
    )
    assert response.status_code == 201, response.text
    shipment_id: str = response.json()["id"]
    return shipment_id


async def _upload_invoice(
    client: AsyncClient, *, shipment_id: str, headers: dict[str, str], lines: list[str]
) -> tuple[str, str]:
    pdf_bytes = build_text_pdf([lines])
    response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": "commercial_invoice"},
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    document_id: str = response.json()["document_id"]
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=document_id,
        headers=headers,
        terminal_statuses=_TERMINAL_DOC_STATUSES,
    )
    return document_id, document["status"]


async def test_telecom_line_item_surfaces_tdra_requirement(client: AsyncClient) -> None:
    """The Phase 5 definition of done: a shipment containing a telecom device
    correctly surfaces the TDRA requirement."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-500001", email="permit1@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-5000-01",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 185.00 USD",
            "Line Item: 24-port managed network switch for a data center | Qty: 1 | "
            "Unit Value: 185.00 USD",
        ],
    )
    await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )

    permits = await wait_for_permits(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(p["regulator"] == "TDRA" for p in items),
    )
    tdra = next(p for p in permits if p["regulator"] == "TDRA")
    assert tdra["permit_type"] == "Telecom equipment type approval"
    assert tdra["estimated_processing_time_days"] == 10
    assert tdra["reference_link"]


async def test_medical_device_surfaces_both_esma_moiat_and_mohap(client: AsyncClient) -> None:
    """implementation plan Section 8's explicit example: medical devices ->
    ESMA/MoIAT + MOHAP."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-500002", email="permit2@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-5000-02",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 500.00 USD",
            "Line Item: Digital stethoscope for doctors | Qty: 1 | Unit Value: 500.00 USD",
        ],
    )
    await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )

    permits = await wait_for_permits(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: len(items) >= 2,
    )
    regulators = {p["regulator"] for p in permits}
    assert regulators == {"MOHAP", "ESMA/MoIAT"}


async def test_regulated_and_non_regulated_items_in_same_shipment(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-500003", email="permit3@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-5000-03",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 1085.00 USD",
            "Line Item: 24-port managed network switch for a data center | Qty: 1 | "
            "Unit Value: 185.00 USD",
            "Line Item: 13-inch laptop computer, 1.1kg, aluminum body | Qty: 1 | "
            "Unit Value: 900.00 USD",
        ],
    )
    await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=2
    )

    permits = await wait_for_permits(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(p["regulator"] == "TDRA" for p in items),
    )
    # Only the network switch line item requires a permit — the laptop doesn't add a
    # second permit or get folded into TDRA's applies_to_line_items.
    assert len(permits) == 1
    assert len(permits[0]["applies_to_line_items"]) == 1


async def test_shipment_with_only_non_regulated_goods_returns_no_permits_required(
    client: AsyncClient,
) -> None:
    """The Phase 5 definition of done: a shipment of ordinary non-regulated goods
    correctly returns no_permits_required: true rather than an ambiguous empty
    response."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-500004", email="permit4@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-5000-04",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 900.00 USD",
            "Line Item: 13-inch laptop computer, 1.1kg, aluminum body | Qty: 1 | "
            "Unit Value: 900.00 USD",
        ],
    )
    await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )

    settled = await wait_for_permits_settled(client, shipment_id=shipment_id, headers=headers)
    assert settled["items"] == []
    assert settled["no_permits_required"] is True


async def test_override_to_a_regulated_hs_code_triggers_permit_retriage(
    client: AsyncClient,
) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-500005", email="permit5@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-5000-05",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 900.00 USD",
            "Line Item: 13-inch laptop computer, 1.1kg, aluminum body | Qty: 1 | "
            "Unit Value: 900.00 USD",
        ],
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    await wait_for_permits_settled(client, shipment_id=shipment_id, headers=headers)
    line_item_id = items[0]["id"]

    override_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/line-items/{line_item_id}/override",
        json={"hs_code": "8517.62", "reason": "Actually a network switch, not a laptop"},
        headers=headers,
    )
    assert override_response.status_code == 200, override_response.text

    permits = await wait_for_permits(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(p["regulator"] == "TDRA" for p in items),
    )
    assert permits[0]["applies_to_line_items"] == [line_item_id]


async def test_company_a_cannot_read_company_bs_permits(client: AsyncClient) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-500006", email="permit6a@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-500007", email="permit6b@example.com"
    )
    headers_b = auth_headers(token_b)
    shipment_b = await _new_shipment(client, headers_b)
    await _upload_invoice(
        client,
        shipment_id=shipment_b,
        headers=headers_b,
        lines=[
            "Invoice Number: INV-5000-06",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 185.00 USD",
            "Line Item: 24-port managed network switch for a data center | Qty: 1 | "
            "Unit Value: 185.00 USD",
        ],
    )
    await wait_for_line_items_classified(
        client, shipment_id=shipment_b, headers=headers_b, expected_count=1
    )
    await wait_for_permits(
        client,
        shipment_id=shipment_b,
        headers=headers_b,
        predicate=lambda items: any(p["regulator"] == "TDRA" for p in items),
    )

    headers_a = auth_headers(token_a)
    response = await client.get(f"/api/v1/shipments/{shipment_b}/permits", headers=headers_a)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
