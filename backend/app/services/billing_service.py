import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.billing_client import get_billing_client
from app.models.enums import SubscriptionStatus
from app.models.subscription import Subscription
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.utils.exceptions import ValidationError

# A small illustrative plan catalog — not sourced from any pricing document. Replace
# with the real plan names/limits once they're settled; keeping this as a plain
# constant (rather than a versioned data file like data/permit_rules/) is deliberate,
# since these aren't externally regulated rules, just an internal product catalog.
_PLAN_SHIPMENTS_PER_MONTH: dict[str, int] = {
    "starter": 20,
    "growth": 100,
    "scale": 500,
}


class BillingService:
    """API-facing. create_checkout and get_subscription are always scoped to the
    caller's own company_id — unlike shipments/documents, a broker never sees a
    managed company's billing (architecture doc Section 14's tenant-isolation
    guarantee extends here too, even though billing isn't itself broker-shareable).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._subscriptions = SubscriptionRepository(session)
        self._shipments = ShipmentRepository(session)
        self._billing_client = get_billing_client()

    async def create_checkout(self, *, company_id: uuid.UUID, plan: str) -> str:
        if plan not in _PLAN_SHIPMENTS_PER_MONTH:
            raise ValidationError(f"Unknown plan: {plan!r}")
        return self._billing_client.create_checkout_session(company_id=company_id, plan=plan)

    async def get_subscription(self, company_id: uuid.UUID) -> tuple[Subscription | None, int]:
        subscription = await self._subscriptions.get_by_company_id(company_id)
        if subscription is None:
            return None, 0
        used = await self._shipments.count_since(company_id, subscription.current_period_start)
        return subscription, used

    async def handle_webhook(self, *, payload: bytes, signature: str) -> None:
        """Verifies the webhook signature and upserts the Subscription row. Relies on
        get_db's commit-on-success behavior (app/config/database.py) — no explicit
        commit here, same as every other plain repository-write service method.

        NOTE: the mock payload carries company_id directly for simplicity. A real
        provider integration would instead resolve the company via a stored
        provider-customer-id -> company_id mapping created during checkout, since a
        real webhook payload has no reason to know Sijil's internal company_id.
        """
        try:
            event = self._billing_client.verify_webhook(payload=payload, signature=signature)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        plan = event["plan"]
        await self._subscriptions.upsert(
            uuid.UUID(event["company_id"]),
            plan=plan,
            status=SubscriptionStatus(event["status"]),
            billing_provider_ref=event.get("billing_provider_ref"),
            shipments_included_per_month=event.get(
                "shipments_included_per_month", _PLAN_SHIPMENTS_PER_MONTH.get(plan, 0)
            ),
            current_period_start=datetime.fromisoformat(event["current_period_start"]),
            current_period_end=datetime.fromisoformat(event["current_period_end"]),
        )
