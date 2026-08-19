import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AccountType, UserRole


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    trade_license_number: str
    account_type: AccountType
    broker_company_id: uuid.UUID | None
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
