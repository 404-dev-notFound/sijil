import uuid

from httpx import AsyncClient


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
