import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionStatus
from app.models.subscription import Subscription


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_company_id(self, company_id: uuid.UUID) -> Subscription | None:
        stmt = select(Subscription).where(Subscription.company_id == company_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        company_id: uuid.UUID,
        *,
        plan: str,
        status: SubscriptionStatus,
        billing_provider_ref: str | None,
        shipments_included_per_month: int,
        current_period_start: datetime,
        current_period_end: datetime,
    ) -> Subscription:
        """Driven exclusively by webhook events (app/services/billing_service.py) —
        never called from the checkout request itself, since the provider (not Sijil)
        is the source of truth for when a subscription actually becomes active."""
        existing = await self.get_by_company_id(company_id)
        if existing is None:
            subscription = Subscription(
                company_id=company_id,
                plan=plan,
                status=status,
                billing_provider_ref=billing_provider_ref,
                shipments_included_per_month=shipments_included_per_month,
                current_period_start=current_period_start,
                current_period_end=current_period_end,
            )
            self._session.add(subscription)
            await self._session.flush()
            return subscription

        existing.plan = plan
        existing.status = status
        existing.billing_provider_ref = billing_provider_ref
        existing.shipments_included_per_month = shipments_included_per_month
        existing.current_period_start = current_period_start
        existing.current_period_end = current_period_end
        await self._session.flush()
        return existing
