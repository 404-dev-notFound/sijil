from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.config.settings import get_settings
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserSummary,
)
from app.services.auth_service import AuthService
from app.utils.exceptions import UnauthenticatedError

router = APIRouter()

_REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    result = await AuthService(db).register(request)
    _set_refresh_cookie(response, result.refresh_token)
    return RegisterResponse(
        company_id=result.user.company_id, user_id=result.user.id, access_token=result.access_token
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await AuthService(db).login(request)
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserSummary.from_user(result.user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if refresh_token is None:
        raise UnauthenticatedError("Missing refresh token.")

    result = await AuthService(db).refresh_from_token(refresh_token)
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserSummary.from_user(result.user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    # Stateless JWT — there's no server-side session to revoke yet. Clearing the
    # httpOnly cookie is sufficient for a browser client; a captured access token still
    # works until it naturally expires (15 min default). A real revocation list (e.g.
    # Redis-backed, keyed by token jti) is a reasonable hardening item once there's a
    # concrete threat model that needs it — not built speculatively here.
    response.delete_cookie(key=_REFRESH_COOKIE_NAME, path="/api/v1/auth")
