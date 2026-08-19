import uuid

from httpx import AsyncClient

from tests.integration.helpers import auth_headers, register_company

_FAKE_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ntrailer\n<< /Root 1 0 R >>\n%%EOF"


async def test_company_a_cannot_read_company_bs_shipment(client: AsyncClient) -> None:
    """The single most important test in Phase 1 (implementation plan Section 4): a
    user from Company A must never be able to read Company B's data, even via a
    crafted request that guesses/knows Company B's real shipment ID."""
    token_a, _ = await register_company(
        client, trade_license_number="DED-100001", email="a@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-100002", email="b@example.com"
    )

    shipment_b = await client.post(
        "/api/v1/shipments", json={"direction": "import"}, headers=auth_headers(token_b)
    )
    shipment_b_id = shipment_b.json()["id"]

    # Company A tries to read Company B's shipment directly by ID.
    response = await client.get(
        f"/api/v1/shipments/{shipment_b_id}", headers=auth_headers(token_a)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_company_a_cannot_list_company_bs_shipments(client: AsyncClient) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-100003", email="a2@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-100004", email="b2@example.com"
    )

    await client.post(
        "/api/v1/shipments", json={"direction": "import"}, headers=auth_headers(token_b)
    )
    await client.post(
        "/api/v1/shipments", json={"direction": "export"}, headers=auth_headers(token_a)
    )

    response = await client.get("/api/v1/shipments", headers=auth_headers(token_a))
    assert response.status_code == 200
    body = response.json()
    assert body["total_items"] == 1
    assert body["items"][0]["direction"] == "export"  # only Company A's own shipment


async def test_company_a_cannot_upload_document_to_company_bs_shipment(
    client: AsyncClient,
) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-100005", email="a3@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-100006", email="b3@example.com"
    )

    shipment_b = await client.post(
        "/api/v1/shipments", json={"direction": "import"}, headers=auth_headers(token_b)
    )
    shipment_b_id = shipment_b.json()["id"]

    response = await client.post(
        f"/api/v1/shipments/{shipment_b_id}/documents",
        data={"doc_type": "commercial_invoice"},
        files={"file": ("invoice.pdf", _FAKE_PDF_BYTES, "application/pdf")},
        headers=auth_headers(token_a),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_broker_cannot_create_shipment_for_unrelated_company(client: AsyncClient) -> None:
    """A broker may only create shipments on_behalf_of_company_id for companies it
    actually manages (Company.broker_company_id) — not an arbitrary company_id."""
    _, unrelated_company_id = await register_company(
        client, trade_license_number="DED-100007", email="unrelated@example.com"
    )
    broker_token, _ = await register_company(
        client,
        trade_license_number="DED-100008",
        email="broker@example.com",
        account_type="broker",
    )

    response = await client.post(
        "/api/v1/shipments",
        json={"direction": "import", "on_behalf_of_company_id": str(unrelated_company_id)},
        headers=auth_headers(broker_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/shipments/{uuid.uuid4()}")
    assert response.status_code == 401  # HTTPBearer's default for a missing header
