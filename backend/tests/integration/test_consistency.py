from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf
from tests.integration.helpers import (
    auth_headers,
    register_company,
    wait_for_discrepancies,
    wait_for_document_status,
)

_TERMINAL_DOC_STATUSES = {"extracted", "needs_manual_review"}


async def _new_shipment(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/v1/shipments", json={"direction": "import"}, headers=headers)
    assert response.status_code == 201, response.text
    shipment_id: str = response.json()["id"]
    return shipment_id


async def _upload(
    client: AsyncClient,
    *,
    shipment_id: str,
    headers: dict[str, str],
    doc_type: str,
    lines: list[str],
) -> str:
    pdf_bytes = build_text_pdf([lines])
    response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": doc_type},
        files={"file": (f"{doc_type}.pdf", pdf_bytes, "application/pdf")},
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
    return document_id


async def test_quantity_mismatch_blocking_and_minor_name_difference_non_blocking(
    client: AsyncClient,
) -> None:
    """The Phase 4 definition of done, both halves in one shipment: a deliberately
    introduced invoice/packing-list quantity mismatch is correctly flagged as
    blocking, while the buyer/consignee name's minor formatting difference ("LLC" vs
    "L.L.C.") is correctly treated as non-blocking (not even flagged)."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-400001", email="cons1@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        lines=[
            "Invoice Number: INV-4000-01",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 1000.00 USD",
            "Line Item: Network switch | Qty: 10 | Unit Value: 100.00 USD",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="packing_list",
        lines=[
            "Packing List Number: PL-4000-01",
            "Total Packages: 12",
            "Total Gross Weight: 200.00 KG",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="bill_of_lading",
        lines=[
            "BL Number: BL-4000-01",
            "Shipper: Shenzhen Tech Co Ltd",
            "Consignee: Al Falah Trading L.L.C.",
        ],
    )

    discrepancies = await wait_for_discrepancies(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(d["field"] == "quantity" for d in items),
    )

    by_field = {d["field"]: d for d in discrepancies}
    assert by_field["quantity"]["severity"] == "blocking"
    assert "10" in by_field["quantity"]["description"]
    assert "12" in by_field["quantity"]["description"]
    # The minor name-formatting difference is not flagged at all in this same
    # settled snapshot.
    assert "buyer_consignee_name" not in by_field
    assert "seller_shipper_name" not in by_field


async def test_substantially_different_shipper_name_is_flagged_as_warning(
    client: AsyncClient,
) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-400002", email="cons2@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        lines=[
            "Invoice Number: INV-4000-02",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 100.00 USD",
            "Line Item: Network switch | Qty: 1 | Unit Value: 100.00 USD",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="packing_list",
        lines=[
            "Packing List Number: PL-4000-02",
            "Total Packages: 1",
            "Total Gross Weight: 5.00 KG",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="bill_of_lading",
        lines=[
            "BL Number: BL-4000-02",
            "Shipper: Globex Industries FZE",
            "Consignee: Al Falah Trading LLC",
        ],
    )

    discrepancies = await wait_for_discrepancies(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(d["field"] == "seller_shipper_name" for d in items),
    )

    by_field = {d["field"]: d for d in discrepancies}
    assert by_field["seller_shipper_name"]["severity"] == "warning"
    assert "quantity" not in by_field
    assert "buyer_consignee_name" not in by_field


async def test_missing_field_on_one_document_is_a_warning(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-400003", email="cons3@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        lines=[
            "Invoice Number: INV-4000-03",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 100.00 USD",
            "Line Item: Network switch | Qty: 1 | Unit Value: 100.00 USD",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="bill_of_lading",
        lines=[
            "BL Number: BL-4000-03",
            "Shipper: Shenzhen Tech Co Ltd",
            "Consignee: Al Falah Trading LLC",
        ],
    )

    discrepancies = await wait_for_discrepancies(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(d["field"] == "seller_shipper_name" for d in items),
    )

    by_field = {d["field"]: d for d in discrepancies}
    assert by_field["seller_shipper_name"]["severity"] == "warning"
    assert "missing" in by_field["seller_shipper_name"]["description"].lower()


async def test_acknowledge_discrepancy_survives_a_recheck(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-400004", email="cons4@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        lines=[
            "Invoice Number: INV-4000-04",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 1000.00 USD",
            "Line Item: Network switch | Qty: 10 | Unit Value: 100.00 USD",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="packing_list",
        lines=[
            "Packing List Number: PL-4000-04",
            "Total Packages: 12",
            "Total Gross Weight: 200.00 KG",
        ],
    )

    discrepancies = await wait_for_discrepancies(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(d["field"] == "quantity" for d in items),
    )
    discrepancy_id = next(d["id"] for d in discrepancies if d["field"] == "quantity")

    ack_response = await client.post(
        f"/api/v1/shipments/{shipment_id}/discrepancies/{discrepancy_id}/acknowledge",
        headers=headers,
    )
    assert ack_response.status_code == 200, ack_response.text
    assert ack_response.json()["acknowledged"] is True
    assert ack_response.json()["acknowledged_at"] is not None

    # Trigger a re-check (a second bill-of-lading upload also fires
    # check_shipment_consistency) and confirm the acknowledgment wasn't wiped.
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="bill_of_lading",
        lines=[
            "BL Number: BL-4000-04",
            "Shipper: Shenzhen Tech Co Ltd",
            "Consignee: Al Falah Trading LLC",
        ],
    )
    refreshed = await wait_for_discrepancies(
        client,
        shipment_id=shipment_id,
        headers=headers,
        predicate=lambda items: any(d["field"] == "quantity" and d["acknowledged"] for d in items),
    )
    quantity_row = next(d for d in refreshed if d["field"] == "quantity")
    assert quantity_row["acknowledged"] is True
    assert quantity_row["severity"] == "blocking"


async def test_company_a_cannot_read_or_acknowledge_company_bs_discrepancies(
    client: AsyncClient,
) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-400005", email="cons5a@example.com"
    )
    token_b, _ = await register_company(
        client, trade_license_number="DED-400006", email="cons5b@example.com"
    )
    headers_b = auth_headers(token_b)
    shipment_b = await _new_shipment(client, headers_b)
    await _upload(
        client,
        shipment_id=shipment_b,
        headers=headers_b,
        doc_type="commercial_invoice",
        lines=[
            "Invoice Number: INV-4000-05",
            "Seller: Shenzhen Tech Co Ltd",
            "Buyer: Al Falah Trading LLC",
            "Total Value: 1000.00 USD",
            "Line Item: Network switch | Qty: 10 | Unit Value: 100.00 USD",
        ],
    )
    await _upload(
        client,
        shipment_id=shipment_b,
        headers=headers_b,
        doc_type="packing_list",
        lines=[
            "Packing List Number: PL-4000-05",
            "Total Packages: 12",
            "Total Gross Weight: 200.00 KG",
        ],
    )
    discrepancies = await wait_for_discrepancies(
        client,
        shipment_id=shipment_b,
        headers=headers_b,
        predicate=lambda items: any(d["field"] == "quantity" for d in items),
    )
    discrepancy_id = next(d["id"] for d in discrepancies if d["field"] == "quantity")

    headers_a = auth_headers(token_a)
    list_response = await client.get(
        f"/api/v1/shipments/{shipment_b}/discrepancies", headers=headers_a
    )
    assert list_response.status_code == 404
    assert list_response.json()["error"]["code"] == "NOT_FOUND"

    ack_response = await client.post(
        f"/api/v1/shipments/{shipment_b}/discrepancies/{discrepancy_id}/acknowledge",
        headers=headers_a,
    )
    assert ack_response.status_code == 404
    assert ack_response.json()["error"]["code"] == "NOT_FOUND"
