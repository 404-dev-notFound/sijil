import httpx
from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf
from tests.integration.helpers import (
    auth_headers,
    register_company,
    wait_for_document_status,
    wait_for_line_items_classified,
    wait_for_report_ready,
)

_TERMINAL_DOC_STATUSES = {"extracted", "needs_manual_review"}

_INVOICE_LINES = [
    "Invoice Number: INV-7000-01",
    "Seller: Test Seller Co",
    "Buyer: Test Buyer LLC",
    "Total Value: 5000.00 USD",
    "Line Item: 24-port managed network switch for a data center | Qty: 1 | "
    "Unit Value: 5000.00 USD",
]


async def _new_shipment(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/shipments",
        json={"direction": "import", "origin_country": "India", "destination_country": "UAE"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    shipment_id: str = response.json()["id"]
    return shipment_id


async def _upload_invoice(
    client: AsyncClient, *, shipment_id: str, headers: dict[str, str]
) -> None:
    pdf_bytes = build_text_pdf([_INVOICE_LINES])
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


async def test_report_generation_produces_a_downloadable_pdf(client: AsyncClient) -> None:
    """The Phase 7 definition of done: triggering a report for an analyzed shipment
    produces a real PDF, downloadable via a short-lived signed URL."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-700001", email="report1@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)
    await _upload_invoice(client, shipment_id=shipment_id, headers=headers)
    await wait_for_line_items_classified(
        client, shipment_id=shipment_id, headers=headers, expected_count=1
    )

    trigger_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/report", headers=headers
    )
    assert trigger_response.status_code == 202, trigger_response.text
    report_id = trigger_response.json()["report_id"]
    assert trigger_response.json()["status"] == "generating"

    report = await wait_for_report_ready(client, report_id=report_id, headers=headers)
    assert report["status"] == "ready"
    assert report["download_url"]
    assert report["generated_at"] is not None

    async with httpx.AsyncClient() as raw_client:
        download_response = await raw_client.get(report["download_url"])
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"%PDF")


async def test_trigger_report_for_nonexistent_shipment_returns_404(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-700002", email="report2@example.com"
    )
    headers = auth_headers(access_token)
    response = await client.post(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000000/report", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_company_a_cannot_trigger_or_read_company_bs_report(client: AsyncClient) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-700003", email="report3a@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-700004", email="report3b@example.com"
    )
    headers_b = auth_headers(token_b)
    shipment_b = await _new_shipment(client, headers_b)
    await _upload_invoice(client, shipment_id=shipment_b, headers=headers_b)
    await wait_for_line_items_classified(
        client, shipment_id=shipment_b, headers=headers_b, expected_count=1
    )

    headers_a = auth_headers(token_a)
    trigger_response = await client.post(
        f"/api/v1/shipments/{shipment_b}/report", headers=headers_a
    )
    assert trigger_response.status_code == 404
    assert trigger_response.json()["error"]["code"] == "NOT_FOUND"

    trigger_response_b = await client.post(
        f"/api/v1/shipments/{shipment_b}/report", headers=headers_b
    )
    assert trigger_response_b.status_code == 202, trigger_response_b.text
    report_id = trigger_response_b.json()["report_id"]
    await wait_for_report_ready(client, report_id=report_id, headers=headers_b)

    get_response = await client.get(f"/api/v1/reports/{report_id}", headers=headers_a)
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "NOT_FOUND"
