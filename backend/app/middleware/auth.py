import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository
from app.utils.security import JWTError, decode_token

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
        )

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id_in_company(
        uuid.UUID(payload["sub"]), uuid.UUID(payload["company_id"])
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def get_accessible_company_ids(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[uuid.UUID]:
    """Resolves the set of company_ids the current user may query against — always
    includes their own company, plus managed companies for broker roles. This is the
    single place that answers "what can this user see," so repositories never have to
    guess (architecture doc Section 14) and route handlers never pass a client-supplied
    company_id straight through to a query.

    NOTE: broker_user is treated identically to broker_admin here (full access to all
    of the broker's managed companies). Restricting a broker_user to a specific subset
    of assigned client companies needs a broker-user-to-company assignment table that
    doesn't exist in the Phase 1 data model — deferred until that's built.
    """
    company_ids = [user.company_id]
    if user.role in (UserRole.BROKER_ADMIN, UserRole.BROKER_USER):
        company_repo = CompanyRepository(db)
        managed = await company_repo.list_managed_companies(user.company_id)
        company_ids.extend(company.id for company in managed)
    return company_ids


def require_role(
    *allowed_roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def _check(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return _check
