import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
from jose import JWTError, jwt

from app.config.settings import get_settings

JWT_ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


def hash_password(plain_password: str) -> str:
    # bcrypt's algorithm only uses the first 72 bytes of the input — enforced by the
    # schema layer (RegisterRequest.admin_password max_length=72), not truncated here,
    # so a too-long password is a validation error, not silent data loss.
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_token(
    *, subject: uuid.UUID, company_id: uuid.UUID, role: str, token_type: TokenType
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_delta = (
        timedelta(minutes=settings.access_token_expire_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_expire_days)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "company_id": str(company_id),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM))


def decode_token(token: str) -> dict[str, Any]:
    """Raises jose.JWTError (caught by callers) on an invalid/expired/malformed token."""
    settings = get_settings()
    decoded: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    return decoded


__all__ = [
    "JWTError",
    "create_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
