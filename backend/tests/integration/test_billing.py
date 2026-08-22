import hashlib
import hmac
import json

import httpx
from httpx import AsyncClient

from app.config.settings import get_settings
from tests.integration.helpers import auth_headers, register_company

_PAST_PERIOD_START = "2020-01-01T00:00:00+00:00"
_FUTURE_PERIOD_END = "2999-01-01T00:00:00+00:00"


def _sign(body_bytes: bytes) -> str:
    secret = get_settings().billing_webhook_secret.encode()
    return hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()


async def _send_webhook(client: AsyncClient, payload: dict) -> httpx.Response:
    body_bytes = json.dumps(payload).encode()
    return await client.post(
        "/api/v1/billing/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Billing-Signature": _sign(body_bytes)},
    )


def _webhook_payload(
    *,
    company_id: str,
    plan: str = "growth",
    status: str = "active",
    period_start: str = _PAST_PERIOD_START,
    period_end: str = _FUTURE_PERIOD_END,
) -> dict:
    return {
        "company_id": company_id,
        "plan": plan,
        "status": status,
        "billing_provider_ref": "mock_sub_123",
        "shipments_included_per_month": 100,
        "current_period_start": period_start,
        "current_period_end": period_end,
    }


async def test_checkout_returns_a_checkout_url(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-710001", email="billing1@example.com"
    )
    response = await client.post(
        "/api/v1/billing/checkout",
        json={"plan": "growth"},
        headers=auth_headers(access_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["checkout_url"].startswith("https://")


async def test_checkout_rejects_unknown_plan(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-710002", email="billing2@example.com"
    )
    response = await client.post(
        "/api/v1/billing/checkout",
        json={"plan": "not-a-real-plan"},
        headers=auth_headers(access_token),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_webhook_activates_subscription_and_get_subscription_reflects_it(
    client: AsyncClient,
) -> None:
    access_token, company_id = await register_company(
        client, trade_license_number="DED-710003", email="billing3@example.com"
    )
    webhook_response = await _send_webhook(
        client, _webhook_payload(company_id=str(company_id))
    )
    assert webhook_response.status_code == 204, webhook_response.text

    get_response = await client.get(
        "/api/v1/billing/subscription", headers=auth_headers(access_token)
    )
    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["plan"] == "growth"
    assert body["status"] == "active"
    assert body["shipments_included_per_month"] == 100
    assert body["shipments_used_this_period"] == 0


async def test_webhook_rejects_invalid_signature(client: AsyncClient) -> None:
    _, company_id = await register_company(
        client, trade_license_number="DED-710004", email="billing4@example.com"
    )
    body_bytes = json.dumps(_webhook_payload(company_id=str(company_id))).encode()
    response = await client.post(
        "/api/v1/billing/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Billing-Signature": "not-a-real-signature"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_get_subscription_without_one_returns_404(client: AsyncClient) -> None:
    access_token, _ = await register_company(
        client, trade_license_number="DED-710005", email="billing5@example.com"
    )
    response = await client.get(
        "/api/v1/billing/subscription", headers=auth_headers(access_token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_company_a_cannot_see_company_bs_subscription(client: AsyncClient) -> None:
    token_a, _ = await register_company(
        client, trade_license_number="DED-710006", email="billing6a@example.com"
    )
    _, company_b_id = await register_company(
        client, trade_license_number="DED-710007", email="billing6b@example.com"
    )
    webhook_response = await _send_webhook(
        client, _webhook_payload(company_id=str(company_b_id))
    )
    assert webhook_response.status_code == 204, webhook_response.text

    response = await client.get(
        "/api/v1/billing/subscription", headers=auth_headers(token_a)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_shipments_used_this_period_reflects_real_shipment_count(
    client: AsyncClient,
) -> None:
    access_token, company_id = await register_company(
        client, trade_license_number="DED-710008", email="billing7@example.com"
    )
    headers = auth_headers(access_token)
    webhook_response = await _send_webhook(
        client, _webhook_payload(company_id=str(company_id))
    )
    assert webhook_response.status_code == 204, webhook_response.text

    for _ in range(3):
        create_response = await client.post(
            "/api/v1/shipments", json={"direction": "import"}, headers=headers
        )
        assert create_response.status_code == 201, create_response.text

    get_response = await client.get("/api/v1/billing/subscription", headers=headers)
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["shipments_used_this_period"] == 3
