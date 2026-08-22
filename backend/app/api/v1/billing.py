from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_current_user, require_role
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.billing import CheckoutRequest, CheckoutResponse, SubscriptionOut
from app.services.billing_service import BillingService
from app.utils.exceptions import NotFoundError

router = APIRouter()


@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionOut:
    subscription, used = await BillingService(db).get_subscription(user.company_id)
    if subscription is None:
        raise NotFoundError("No subscription found for this company.")
    return SubscriptionOut(
        plan=subscription.plan,
        status=subscription.status,
        shipments_included_per_month=subscription.shipments_included_per_month,
        shipments_used_this_period=used,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    user: Annotated[User, Depends(require_role(UserRole.COMPANY_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckoutResponse:
    checkout_url = await BillingService(db).create_checkout(
        company_id=user.company_id, plan=request.plan
    )
    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def billing_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_billing_signature: Annotated[str, Header()],
) -> None:
    """Called by the billing provider, never by an authenticated Sijil user — verified
    via HMAC signature (app/integrations/billing_client.py), not a bearer token."""
    payload = await request.body()
    await BillingService(db).handle_webhook(payload=payload, signature=x_billing_signature)
