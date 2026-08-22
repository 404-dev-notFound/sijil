import hashlib
import hmac
import json
import uuid
from typing import Any, Protocol

from app.config.settings import get_settings


class BillingClient(Protocol):
    """Swappable billing provider interface, same rationale as LLMClient (architecture
    doc Section 8). Sijil never collects card details directly (architecture doc
    Section 15) — this is purely a hosted-checkout + webhook-verification boundary; the
    provider itself is the source of truth for subscription state.
    """

    def create_checkout_session(self, *, company_id: uuid.UUID, plan: str) -> str: ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]: ...


class MockBillingClient:
    """Deterministic stand-in for local dev/testing — never calls a real payment
    provider. create_checkout_session returns a fake hosted-checkout URL rather than
    performing a real redirect; a "completed checkout" is simulated by POSTing a
    correctly HMAC-signed webhook payload to /billing/webhook directly, the same way
    `stripe trigger` synthesizes provider events against a real integration.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def create_checkout_session(self, *, company_id: uuid.UUID, plan: str) -> str:
        session_id = uuid.uuid4()
        return (
            f"https://billing.mock.sijil.local/checkout/{session_id}"
            f"?company_id={company_id}&plan={plan}"
        )

    def verify_webhook(self, *, payload: bytes, signature: str) -> dict[str, Any]:
        expected = hmac.new(
            self._settings.billing_webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid webhook signature.")
        parsed: dict[str, Any] = json.loads(payload)
        return parsed


def get_billing_client() -> BillingClient:
    settings = get_settings()
    if settings.billing_provider == "mock":
        return MockBillingClient()
    raise NotImplementedError(f"Unsupported BILLING_PROVIDER: {settings.billing_provider!r}")
