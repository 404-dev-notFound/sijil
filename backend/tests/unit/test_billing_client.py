import hashlib
import hmac
import json

import pytest

from app.config.settings import get_settings
from app.integrations.billing_client import MockBillingClient


def _sign(body_bytes: bytes) -> str:
    secret = get_settings().billing_webhook_secret.encode()
    return hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()


def test_verify_webhook_accepts_a_correctly_signed_payload() -> None:
    client = MockBillingClient()
    payload = {"event": "checkout.session.completed", "plan": "growth"}
    body_bytes = json.dumps(payload).encode()

    result = client.verify_webhook(payload=body_bytes, signature=_sign(body_bytes))

    assert result == payload


def test_verify_webhook_rejects_a_bad_signature() -> None:
    client = MockBillingClient()
    body_bytes = json.dumps({"plan": "growth"}).encode()

    with pytest.raises(ValueError):
        client.verify_webhook(payload=body_bytes, signature="0" * 64)


def test_verify_webhook_rejects_a_payload_that_was_tampered_with_after_signing() -> None:
    client = MockBillingClient()
    original = json.dumps({"plan": "growth"}).encode()
    signature = _sign(original)
    tampered = json.dumps({"plan": "scale"}).encode()

    with pytest.raises(ValueError):
        client.verify_webhook(payload=tampered, signature=signature)
