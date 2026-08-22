from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf
from tests.integration.helpers import auth_headers, register_company, wait_for_document_status

_INVOICE_PDF_BYTES = build_text_pdf(
    [
        [
            "Invoice Number: INV-2026-0001",
            "Seller: Test Seller Co",
            "Buyer: Test Buyer LLC",
            "Total Value: 100.00 USD",
        ]
    ]
)


async def test_register_login_create_shipment_and_upload_document(client: AsyncClient) -> None:
    """Phase 1 definition of done, end to end: register -> log in -> create a
    shipment -> upload a document that's durably stored (real MinIO, not mocked). Also
    confirms the Phase 2 extraction pipeline (real Celery worker) picks it up and
    carries it through to a terminal status."""
    access_token, company_id = await register_company(
        client, trade_license_number="DED-000001", email="owner@example.com"
    )

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "SuperSecret123"},
    )
    assert login_response.status_code == 200, login_response.text
    login_body = login_response.json()
    access_token = login_body["access_token"]
    assert login_body["user"]["company_id"] == str(company_id)

    headers = auth_headers(access_token)

    shipment_response = await client.post(
        "/api/v1/shipments",
        json={"direction": "import", "notes": "test shipment"},
        headers=headers,
    )
    assert shipment_response.status_code == 201, shipment_response.text
    shipment = shipment_response.json()
    assert shipment["company_id"] == str(company_id)
    assert shipment["status"] == "created"
    shipment_id = shipment["id"]

    upload_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": "commercial_invoice"},
        files={"file": ("invoice.pdf", _INVOICE_PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert upload_response.status_code == 202, upload_response.text
    document = upload_response.json()
    assert document["status"] == "queued"

    processed = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=document["document_id"],
        headers=headers,
        terminal_statuses={"extracted", "needs_manual_review"},
    )
    assert processed["status"] == "extracted"
    assert processed["extracted_fields"]["invoice_number"] == "INV-2026-0001"

    detail_response = await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "extracting"  # extracted; awaiting Phase 3 classification
    assert len(detail["documents"]) == 1
    assert detail["documents"][0]["id"] == document["document_id"]
    assert detail["documents"][0]["original_filename"] == "invoice.pdf"


async def test_upload_rejects_corrupt_file_before_queueing(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-000002", email="owner2@example.com"
    )
    headers = auth_headers(access_token)
    shipment_response = await client.post(
        "/api/v1/shipments", json={"direction": "export"}, headers=headers
    )
    shipment_id = shipment_response.json()["id"]

    upload_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": "commercial_invoice"},
        files={"file": ("not-a-real-file.pdf", b"this is not a pdf", "application/pdf")},
        headers=headers,
    )
    assert upload_response.status_code == 422
    assert upload_response.json()["error"]["code"] == "UNPROCESSABLE"


async def test_register_rejects_duplicate_trade_license(client: AsyncClient) -> None:
    await register_company(client, trade_license_number="DED-000003", email="first@example.com")
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "company_legal_name": "Another Co",
            "trade_license_number": "DED-000003",
            "account_type": "trading_company",
            "admin_email": "second@example.com",
            "admin_password": "SuperSecret123",
            "admin_full_name": "Someone Else",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    await register_company(client, trade_license_number="DED-000004", email="owner4@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner4@example.com", "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
