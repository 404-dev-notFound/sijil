import asyncio
import uuid
from collections.abc import Callable

from httpx import AsyncClient

_POLL_INTERVAL_SECONDS = 0.2
_DEFAULT_POLL_TIMEOUT_SECONDS = 10.0


async def register_company(
    client: AsyncClient,
    *,
    trade_license_number: str,
    email: str,
    account_type: str = "trading_company",
) -> tuple[str, uuid.UUID]:
    """Registers a company + admin user, returns (access_token, company_id)."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "company_legal_name": f"Test Co {trade_license_number}",
            "trade_license_number": trade_license_number,
            "account_type": account_type,
            "admin_email": email,
            "admin_password": "SuperSecret123",
            "admin_full_name": "Test Admin",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["access_token"], uuid.UUID(body["company_id"])


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def wait_for_document_status(
    client: AsyncClient,
    *,
    shipment_id: str,
    document_id: str,
    headers: dict[str, str],
    terminal_statuses: set[str],
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> dict:
    """Polls GET .../documents/{id} until the real Celery worker (a genuine separate
    process — see .github/workflows/ci.yml) finishes processing and the document
    reaches one of terminal_statuses, or raises if it doesn't within timeout."""
    elapsed = 0.0
    while elapsed < timeout:
        response = await client.get(
            f"/api/v1/shipments/{shipment_id}/documents/{document_id}", headers=headers
        )
        assert response.status_code == 200, response.text
        document = response.json()
        if document["status"] in terminal_statuses:
            return document
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"document {document_id} did not reach {terminal_statuses} within {timeout}s "
        f"(last status: {document['status']!r})"
    )


async def wait_for_line_items_classified(
    client: AsyncClient,
    *,
    shipment_id: str,
    headers: dict[str, str],
    expected_count: int,
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> list[dict]:
    """Polls GET .../line-items until the real classification worker has produced a
    classification for every expected line item (or raises if it doesn't within
    timeout)."""
    elapsed = 0.0
    items: list[dict] = []
    while elapsed < timeout:
        response = await client.get(
            f"/api/v1/shipments/{shipment_id}/line-items", headers=headers
        )
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        if len(items) >= expected_count and all(item["classification"] for item in items):
            return items
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"line items for shipment {shipment_id} did not all reach a classified state "
        f"within {timeout}s (last seen: {items!r})"
    )


async def wait_for_discrepancies(
    client: AsyncClient,
    *,
    shipment_id: str,
    headers: dict[str, str],
    predicate: Callable[[list[dict]], bool],
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> list[dict]:
    """Polls GET .../discrepancies until predicate(items) is True, or raises if it
    isn't within timeout. A plain count/emptiness check doesn't work here — zero
    discrepancies is itself a valid settled state, indistinguishable from "hasn't run
    yet" — so the caller supplies whatever positive condition its scenario expects to
    eventually become true (e.g. "the quantity discrepancy has appeared"), and can then
    safely assert on the rest of that same settled snapshot."""
    elapsed = 0.0
    items: list[dict] = []
    while elapsed < timeout:
        response = await client.get(
            f"/api/v1/shipments/{shipment_id}/discrepancies", headers=headers
        )
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        if predicate(items):
            return items
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"discrepancies for shipment {shipment_id} never satisfied the predicate "
        f"within {timeout}s (last seen: {items!r})"
    )
