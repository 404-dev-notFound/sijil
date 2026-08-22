from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf
from tests.integration.helpers import (
    auth_headers,
    register_company,
    wait_for_document_status,
    wait_for_line_items_classified,
    wait_for_origin_determination,
)

_TERMINAL_DOC_STATUSES = {"extracted", "needs_manual_review"}


async def _new_shipment(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    origin_country: str | None = None,
    destination_country: str | None = None,
) -> str:
    payload: dict[str, str] = {"direction": "import"}
    if origin_country is not None:
        payload["origin_country"] = origin_country
    if destination_country is not None:
        payload["destination_country"] = destination_country
    response = await client.post("/api/v1/shipments", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    shipment_id: str = response.json()["id"]
    return shipment_id


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
    document_id: str = response.json()["document_id"]
    await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=document_id,
        headers=headers,
        terminal_statuses=_TERMINAL_DOC_STATUSES,
    )


_NETWORK_SWITCH_INVOICE = [
    "Invoice Number: INV-6000-01",
    "Seller: Test Seller Co",
    "Buyer: Test Buyer LLC",
    "Total Value: 10000.00 USD",
    "Line Item: 24-port managed network switch for a data center | Qty: 1 | "
    "Unit Value: 10000.00 USD",
]


async def test_qualifying_shipment_determines_eligibility_and_savings(
    client: AsyncClient,
) -> None:
    """The Phase 6 definition of done: a sample shipment with known origin data
    correctly determines CEPA eligibility and estimated savings."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-600001", email="cepa1@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(
        client, headers, origin_country="India", destination_country="UAE"
    )

    await _upload_invoice(
        client, shipment_id=shipment_id, headers=headers, lines=_NETWORK_SWITCH_INVOICE
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    line_item_id = items[0]["id"]

    breakdown_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/line-items/{line_item_id}/origin/value-breakdown",
        json={
            "local_content_value": {"amount": "4200.00", "currency": "USD"},
            "total_value": {"amount": "10000.00", "currency": "USD"},
        },
        headers=headers,
    )
    assert breakdown_response.status_code == 200, breakdown_response.text

    determination = await wait_for_origin_determination(
        client,
        shipment_id=shipment_id,
        line_item_id=line_item_id,
        headers=headers,
        predicate=lambda body: body["qualifies"] == "qualifies",
    )
    assert determination["agreement"] == "UAE-India CEPA"
    assert "42%" in determination["reasoning"]
    assert determination["estimated_duty_savings"] == {"amount": "500.00", "currency": "USD"}
    assert determination["required_documents"] == [
        "Preferential Certificate of Origin (India)"
    ]


async def test_missing_value_breakdown_returns_insufficient_data(
    client: AsyncClient,
) -> None:
    """The Phase 6 definition of done: a shipment with missing value data correctly
    prompts for the missing input rather than guessing does_not_qualify."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-600002", email="cepa2@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(
        client, headers, origin_country="India", destination_country="UAE"
    )

    await _upload_invoice(
        client, shipment_id=shipment_id, headers=headers, lines=_NETWORK_SWITCH_INVOICE
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    line_item_id = items[0]["id"]

    determination = await wait_for_origin_determination(
        client, shipment_id=shipment_id, line_item_id=line_item_id, headers=headers
    )
    assert determination["qualifies"] == "insufficient_data"
    assert set(determination["missing_fields"]) == {"local_content_value", "total_value"}
    assert determination["estimated_duty_savings"] is None


async def test_shipment_without_country_pair_is_not_applicable(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-600003", email="cepa3@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)  # no origin/destination_country

    await _upload_invoice(
        client, shipment_id=shipment_id, headers=headers, lines=_NETWORK_SWITCH_INVOICE
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )
    line_item_id = items[0]["id"]

    determination = await wait_for_origin_determination(
        client, shipment_id=shipment_id, line_item_id=line_item_id, headers=headers
    )
    assert determination["qualifies"] == "not_applicable"
    assert determination["agreement"] is None


async def test_uncovered_hs_code_for_the_stated_origin_is_not_applicable(
    client: AsyncClient,
) -> None:
    """A laptop is covered under UAE-Indonesia CEPA but not UAE-India CEPA — stating
    India as the origin country for a laptop shipment correctly yields no applicable
    agreement rather than silently reusing Indonesia's rule."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-600004", email="cepa4@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(
        client, headers, origin_country="India", destination_country="UAE"
    )

    await _upload_invoice(
        client,
        shipment_id=shipment_id,
        headers=headers,
        lines=[
            "Invoice Number: INV-6000-04",
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

    determination = await wait_for_origin_determination(
        client, shipment_id=shipment_id, line_item_id=line_item_id, headers=headers
    )
    assert determination["qualifies"] == "not_applicable"


async def test_company_a_cannot_read_or_submit_breakdown_for_company_bs_line_item(
    client: AsyncClient,
) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-600005", email="cepa5a@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-600006", email="cepa5b@example.com"
    )
    headers_b = auth_headers(token_b)
    shipment_b = await _new_shipment(
        client, headers_b, origin_country="India", destination_country="UAE"
    )
    await _upload_invoice(
        client, shipment_id=shipment_b, headers=headers_b, lines=_NETWORK_SWITCH_INVOICE
    )
    items = await wait_for_line_items_classified(
        client, shipment_id=shipment_b, headers=headers_b, expected_count=1
    )
    line_item_id = items[0]["id"]
    await wait_for_origin_determination(
        client, shipment_id=shipment_b, line_item_id=line_item_id, headers=headers_b
    )

    headers_a = auth_headers(token_a)
    get_response = await client.get(
        f"/api/v1/shipments/{shipment_b}/line-items/{line_item_id}/origin",
        headers=headers_a,
    )
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "NOT_FOUND"

    post_response = await client.post(
        f"/api/v1/shipments/{shipment_b}/line-items/{line_item_id}/origin/value-breakdown",
        json={
            "local_content_value": {"amount": "100.00", "currency": "USD"},
            "total_value": {"amount": "200.00", "currency": "USD"},
        },
        headers=headers_a,
    )
    assert post_response.status_code == 404
    assert post_response.json()["error"]["code"] == "NOT_FOUND"
