import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.models.company import Company
from app.models.enums import AccountType, UserRole
from app.models.user import User
from app.repositories.company_repository import CompanyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.utils.exceptions import ConflictError, UnauthenticatedError
from app.utils.security import JWTError, create_token, decode_token, hash_password, verify_password


@dataclass
class AuthResult:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int


def _issue_tokens(user: User) -> AuthResult:
    settings = get_settings()
    access_token = create_token(
        subject=user.id, company_id=user.company_id, role=user.role, token_type="access"
    )
    refresh_token = create_token(
        subject=user.id, company_id=user.company_id, role=user.role, token_type="refresh"
    )
    return AuthResult(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._companies = CompanyRepository(session)
        self._users = UserRepository(session)

    async def register(self, request: RegisterRequest) -> AuthResult:
        existing_company = await self._companies.get_by_trade_license_number(
            request.trade_license_number
        )
        if existing_company is not None:
            raise ConflictError(
                "A company with this trade license number is already registered.",
                details={"field": "trade_license_number"},
            )

        existing_user = await self._users.get_by_email(request.admin_email)
        if existing_user is not None:
            raise ConflictError(
                "A user with this email is already registered.",
                details={"field": "admin_email"},
            )

        company = await self._companies.create(
            Company(
                legal_name=request.company_legal_name,
                trade_license_number=request.trade_license_number,
                account_type=request.account_type,
            )
        )
        await self._session.flush()  # company.id must exist before the FK on User

        admin_role = (
            UserRole.BROKER_ADMIN
            if request.account_type == AccountType.BROKER
            else UserRole.COMPANY_ADMIN
        )
        user = await self._users.create(
            User(
                company_id=company.id,
                email=request.admin_email,
                hashed_password=hash_password(request.admin_password),
                full_name=request.admin_full_name,
                role=admin_role,
            )
        )
        return _issue_tokens(user)

    async def login(self, request: LoginRequest) -> AuthResult:
        user = await self._users.get_by_email(request.email)
        if (
            user is None
            or not user.is_active
            or not verify_password(request.password, user.hashed_password)
        ):
            raise UnauthenticatedError("Invalid email or password.")

        return _issue_tokens(user)

    async def refresh_from_token(self, refresh_token: str) -> AuthResult:
        """Auth is the refresh token itself (from the httpOnly cookie), not a Bearer
        access token — that's the whole point of this endpoint (API SPEC Section 4:
        "Auth: Refresh token cookie"). Issues a brand-new refresh token too (rotation),
        not just a new access token."""
        try:
            payload = decode_token(refresh_token)
        except JWTError as exc:
            raise UnauthenticatedError("Invalid or expired refresh token.") from exc

        if payload.get("type") != "refresh":
            raise UnauthenticatedError("Invalid token type.")

        user = await self._users.get_by_id_in_company(
            uuid.UUID(payload["sub"]), uuid.UUID(payload["company_id"])
        )
        if user is None or not user.is_active:
            raise UnauthenticatedError("Invalid refresh token.")
        return _issue_tokens(user)
