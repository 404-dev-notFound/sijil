import uuid

import pytest
from fastapi import HTTPException

from app.middleware.auth import require_role
from app.models.enums import UserRole
from app.models.user import User


def _user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        email="user@example.com",
        hashed_password="irrelevant",
        full_name="Test User",
        role=role,
        is_active=True,
    )


async def test_allows_a_user_with_an_allowed_role() -> None:
    check = require_role(UserRole.COMPANY_ADMIN)
    admin = _user(UserRole.COMPANY_ADMIN)

    result = await check(admin)

    assert result is admin


async def test_rejects_a_user_without_an_allowed_role() -> None:
    check = require_role(UserRole.COMPANY_ADMIN)
    non_admin = _user(UserRole.COMPANY_USER)

    with pytest.raises(HTTPException) as exc_info:
        await check(non_admin)

    assert exc_info.value.status_code == 403
