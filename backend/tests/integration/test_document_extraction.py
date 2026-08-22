import json

from httpx import AsyncClient

from tests.fixtures.pdf_builder import build_text_pdf, fake_scanned_image_bytes
from tests.integration.helpers import auth_headers, register_company, wait_for_document_status

_EXTRACTED = {"extracted"}
_NEEDS_REVIEW = {"needs_manual_review"}
_TERMINAL = _EXTRACTED | _NEEDS_REVIEW


async def _upload(
    client: AsyncClient,
    *,
    shipment_id: str,
    headers: dict[str, str],
    doc_type: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> dict:
    response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": doc_type},
        files={"file": (filename, file_bytes, content_type)},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _new_shipment(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/shipments", json={"direction": "import"}, headers=headers
    )
    assert response.status_code == 201, response.text
    shipment_id: str = response.json()["id"]
    return shipment_id


async def test_clean_native_pdf_commercial_invoice_is_extracted(client: AsyncClient) -> None:
    """Sample document 1/10 — clean native-text PDF, all expected fields present."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200001", email="ext1@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "Invoice Number: INV-2026-0451",
                "Seller: Shenzhen Tech Co Ltd",
                "Buyer: Al Falah Trading LLC",
                "Total Value: 18500.00 USD",
            ]
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="invoice.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )

    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"
    assert document["extraction_confidence"] == 1.0
    assert document["extracted_fields"]["invoice_number"] == "INV-2026-0451"
    assert document["extracted_fields"]["seller"] == "Shenzhen Tech Co Ltd"
    assert document["extracted_fields"]["buyer"] == "Al Falah Trading LLC"
    assert document["extracted_fields"]["total_value"] == {"amount": "18500.00", "currency": "USD"}

    shipment = (await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)).json()
    assert shipment["status"] == "extracting"  # all extracted; awaiting Phase 3 classification


async def test_second_clean_invoice_different_currency_is_extracted(
    client: AsyncClient,
) -> None:
    """Sample document 2/10."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200002", email="ext2@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "Invoice Number: INV-2026-0777",
                "Seller: Gulf Traders FZE",
                "Buyer: Emirates Import LLC",
                "Total Value: 42300.50 AED",
            ]
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="invoice2.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"
    assert document["extracted_fields"]["total_value"] == {"amount": "42300.50", "currency": "AED"}


async def test_clean_packing_list_is_extracted(client: AsyncClient) -> None:
    """Sample document 3/10."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200003", email="ext3@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "Packing List Number: PL-2026-0451",
                "Total Packages: 12",
                "Total Gross Weight: 340.50 KG",
            ]
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="packing_list",
        filename="packing_list.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"
    assert document["extracted_fields"]["total_packages"] == "12"


async def test_partial_packing_list_just_below_threshold_needs_review(
    client: AsyncClient,
) -> None:
    """Sample document 4/10 — 2 of 3 expected fields present (0.67 confidence), just
    below the 0.7 threshold: a deliberate boundary case for the confidence-threshold
    logic (implementation plan Section 5)."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200004", email="ext4@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [["Packing List Number: PL-2026-0999", "Total Packages: 4"]]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="packing_list",
        filename="partial_packing_list.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "needs_manual_review"
    assert document["extraction_confidence"] == 0.67

    shipment = (await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)).json()
    assert shipment["status"] == "needs_manual_review"


async def test_clean_bill_of_lading_is_extracted(client: AsyncClient) -> None:
    """Sample document 5/10."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200005", email="ext5@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "BL Number: BL-2026-0451",
                "Shipper: Shenzhen Tech Co Ltd",
                "Consignee: Al Falah Trading LLC",
            ]
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="bill_of_lading",
        filename="bol.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"
    assert document["extracted_fields"]["bl_number"] == "BL-2026-0451"


async def test_clean_air_waybill_is_extracted(client: AsyncClient) -> None:
    """Sample document 6/10."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200006", email="ext6@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "AWB Number: 176-12345678",
                "Shipper: Shenzhen Tech Co Ltd",
                "Consignee: Al Falah Trading LLC",
            ]
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="air_waybill",
        filename="awb.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"
    assert document["extracted_fields"]["awb_number"] == "176-12345678"


async def test_multi_page_invoice_fields_concatenate_across_pages(
    client: AsyncClient,
) -> None:
    """Sample document 7/10 — fields split across two PDF pages, proving the native-text
    extraction reads and concatenates every page rather than just the first."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200007", email="ext7@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            ["Invoice Number: INV-2026-0999", "Seller: Multi Page Trading Co"],
            ["Buyer: Al Falah Trading LLC", "Total Value: 9999.00 AED"],
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="multipage_invoice.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"
    assert document["extraction_confidence"] == 1.0
    assert document["extracted_fields"]["seller"] == "Multi Page Trading Co"
    assert document["extracted_fields"]["total_value"] == {"amount": "9999.00", "currency": "AED"}


async def test_low_quality_native_pdf_with_one_field_needs_review(client: AsyncClient) -> None:
    """Sample document 8/10 — only 1 of 4 expected invoice fields readable (0.25
    confidence): simulates a poor-quality native PDF, well below the threshold."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200008", email="ext8@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf([["Invoice Number: INV-2026-0001"]])
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="low_quality_invoice.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "needs_manual_review"
    assert document["extraction_confidence"] == 0.25


async def test_scanned_image_with_no_live_ocr_needs_review(client: AsyncClient) -> None:
    """Sample document 9/10 — a scanned/low-quality image. With no live OCR provider
    configured (LLM_PROVIDER=mock in this test environment), this is honestly flagged
    needs_manual_review rather than pretending to have read it — never a
    false-confident guess (architecture doc "Do Not Do This" rules)."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200009", email="ext9@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="scanned_invoice.jpg",
        file_bytes=fake_scanned_image_bytes(),
        content_type="image/jpeg",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "needs_manual_review"
    assert document["extraction_confidence"] == 0.0
    assert document["extracted_fields"] == {}


async def test_scanned_arabic_document_with_no_live_ocr_needs_review(
    client: AsyncClient,
) -> None:
    """Sample document 10/10 — a scanned Arabic-language invoice (implementation plan
    Section 5's non-English fixture requirement). Same honest outcome as any other
    scanned document without a live OCR provider: needs_manual_review, not a guess."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200010", email="ext10@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="scanned_arabic_invoice.jpg",
        file_bytes=fake_scanned_image_bytes(),
        content_type="image/jpeg",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "needs_manual_review"


async def test_corrupted_file_rejected_before_reaching_queue(client: AsyncClient) -> None:
    """Definition of done: a deliberately corrupted file is rejected with a clear 422
    before ever reaching the queue (architecture doc Section 31 edge case) — no
    document row is created and no worker task is ever enqueued."""
    access_token, _ = await register_company(
        client, trade_license_number="DED-200011", email="ext11@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    response = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        data={"doc_type": "commercial_invoice"},
        files={"file": ("garbage.pdf", b"this is definitely not a pdf", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNPROCESSABLE"

    shipment = (await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)).json()
    assert shipment["documents"] == []


async def test_manual_correction_moves_document_and_shipment_out_of_review(
    client: AsyncClient,
) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-200012", email="ext12@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf([["Invoice Number: INV-2026-0002"]])
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="needs_review_invoice.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "needs_manual_review"

    correction_response = await client.patch(
        f"/api/v1/shipments/{shipment_id}/documents/{upload['document_id']}",
        json={
            "extracted_fields": {
                "seller": "Shenzhen Tech Co Ltd",
                "buyer": "Al Falah Trading LLC",
                "total_value": {"amount": "18500.00", "currency": "USD"},
            }
        },
        headers=headers,
    )
    assert correction_response.status_code == 200, correction_response.text
    corrected = correction_response.json()
    assert corrected["status"] == "extracted"
    assert corrected["extracted_fields"]["invoice_number"] == "INV-2026-0002"
    assert corrected["extracted_fields"]["seller"] == "Shenzhen Tech Co Ltd"

    shipment = (await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)).json()
    assert shipment["status"] == "extracting"


async def test_correction_rejected_when_document_not_in_needs_review(
    client: AsyncClient,
) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-200013", email="ext13@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "Invoice Number: INV-2026-0003",
                "Seller: Shenzhen Tech Co Ltd",
                "Buyer: Al Falah Trading LLC",
                "Total Value: 100.00 USD",
            ]
        ]
    )
    upload = await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="already_extracted.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )
    document = await wait_for_document_status(
        client,
        shipment_id=shipment_id,
        document_id=upload["document_id"],
        headers=headers,
        terminal_statuses=_TERMINAL,
    )
    assert document["status"] == "extracted"

    correction_response = await client.patch(
        f"/api/v1/shipments/{shipment_id}/documents/{upload['document_id']}",
        json={"extracted_fields": {"seller": "Someone Else"}},
        headers=headers,
    )
    assert correction_response.status_code == 409
    assert correction_response.json()["error"]["code"] == "CONFLICT"


async def test_sse_stream_reports_status_transitions(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-200014", email="ext14@example.com"
    )
    headers = auth_headers(access_token)
    shipment_id = await _new_shipment(client, headers)

    pdf_bytes = build_text_pdf(
        [
            [
                "Invoice Number: INV-2026-0004",
                "Seller: Shenzhen Tech Co Ltd",
                "Buyer: Al Falah Trading LLC",
                "Total Value: 100.00 USD",
            ]
        ]
    )
    await _upload(
        client,
        shipment_id=shipment_id,
        headers=headers,
        doc_type="commercial_invoice",
        filename="sse_invoice.pdf",
        file_bytes=pdf_bytes,
        content_type="application/pdf",
    )

    # "extracting" covers both "a document is currently being processed" and "every
    # document is done" — Phase 2 has no distinct "all done" status yet (that's what
    # Phase 3's classifying transition adds), so once we observe it there's nothing
    # further this stream will ever emit on its own; stop there rather than waiting
    # for a status change that isn't coming.
    seen_statuses: list[str] = []
    async with client.stream(
        "GET", f"/api/v1/shipments/{shipment_id}/events", headers=headers
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                payload = json.loads(line.removeprefix("data: "))
                seen_statuses.append(payload["status"])
                if payload["status"] == "extracting":
                    break
            if len(seen_statuses) >= 5:
                break

    assert seen_statuses[0] in {"documents_uploading", "extracting"}
    assert seen_statuses[-1] == "extracting"


async def test_sse_stream_returns_404_for_inaccessible_shipment(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-200015", email="ext15@example.com"
    )
    headers = auth_headers(access_token)

    response = await client.get(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000000/events", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
