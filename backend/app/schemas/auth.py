import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AccountType, UserRole
from app.models.user import User


class RegisterRequest(BaseModel):
    company_legal_name: str = Field(min_length=1, max_length=255)
    trade_license_number: str = Field(min_length=1, max_length=100)
    account_type: AccountType
    admin_email: EmailStr
    # bcrypt only uses the first 72 bytes of a password — capped here so an
    # over-length password is a clear 400 validation error, not silent truncation.
    admin_password: str = Field(min_length=8, max_length=72)
    admin_full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserSummary(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    role: UserRole

    @classmethod
    def from_user(cls, user: User) -> "UserSummary":
        return cls(id=user.id, company_id=user.company_id, role=user.role)


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    user: UserSummary


class RegisterResponse(BaseModel):
    company_id: uuid.UUID
    user_id: uuid.UUID
    access_token: str
    refresh_token_set: bool = True
