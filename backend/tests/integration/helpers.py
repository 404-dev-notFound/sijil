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


async def wait_for_permits(
    client: AsyncClient,
    *,
    shipment_id: str,
    headers: dict[str, str],
    predicate: Callable[[list[dict]], bool],
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> list[dict]:
    """Polls GET .../permits until predicate(items) is True — same rationale as
    wait_for_discrepancies (zero permits is itself a valid settled state)."""
    elapsed = 0.0
    items: list[dict] = []
    while elapsed < timeout:
        response = await client.get(f"/api/v1/shipments/{shipment_id}/permits", headers=headers)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        if predicate(items):
            return items
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"permits for shipment {shipment_id} never satisfied the predicate within "
        f"{timeout}s (last seen: {items!r})"
    )


async def wait_for_permits_settled(
    client: AsyncClient,
    *,
    shipment_id: str,
    headers: dict[str, str],
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> dict:
    """Polls GET .../permits until two consecutive reads return an identical result —
    used specifically for a "no permits required at all" scenario, where the expected
    end state (empty items) is indistinguishable by content alone from "triage hasn't
    run yet"."""
    elapsed = 0.0
    previous: dict | None = None
    current: dict = {}
    while elapsed < timeout:
        response = await client.get(f"/api/v1/shipments/{shipment_id}/permits", headers=headers)
        assert response.status_code == 200, response.text
        current = response.json()
        if current == previous:
            return current
        previous = current
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"permits for shipment {shipment_id} never stabilized within {timeout}s "
        f"(last seen: {current!r})"
    )


async def wait_for_report_ready(
    client: AsyncClient,
    *,
    report_id: str,
    headers: dict[str, str],
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> dict:
    """Polls GET /reports/{id} until the real Celery worker finishes PDF generation
    and the report reaches a terminal status (ready or failed)."""
    elapsed = 0.0
    report: dict = {}
    while elapsed < timeout:
        response = await client.get(f"/api/v1/reports/{report_id}", headers=headers)
        assert response.status_code == 200, response.text
        report = response.json()
        if report["status"] in {"ready", "failed"}:
            return report
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"report {report_id} did not reach a terminal status within {timeout}s "
        f"(last status: {report['status']!r})"
    )


async def wait_for_origin_determination(
    client: AsyncClient,
    *,
    shipment_id: str,
    line_item_id: str,
    headers: dict[str, str],
    predicate: Callable[[dict], bool] = lambda _: True,
    timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
) -> dict:
    """Polls GET .../origin until it returns 200 and predicate(body) is True. Unlike
    permits/discrepancies, "doesn't exist yet" here is a real 404 (CEPAOriginService
    always creates a row once it runs at all, even a NOT_APPLICABLE/INSUFFICIENT_DATA
    one), so a 404 just means keep polling rather than a settled empty state."""
    elapsed = 0.0
    last_status = 0
    body: dict = {}
    while elapsed < timeout:
        response = await client.get(
            f"/api/v1/shipments/{shipment_id}/line-items/{line_item_id}/origin",
            headers=headers,
        )
        last_status = response.status_code
        if response.status_code == 200:
            body = response.json()
            if predicate(body):
                return body
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise AssertionError(
        f"origin determination for line item {line_item_id} never satisfied the "
        f"predicate within {timeout}s (last status: {last_status}, last body: {body!r})"
    )
