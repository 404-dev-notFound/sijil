import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AccountType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.subscription import Subscription
    from app.models.user import User


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_license_number: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type"), nullable=False
    )

    # Set only for a company managed by a broker; the broker itself has this as None.
    # See architecture doc Section 14 — broker access to a managed company is always
    # checked via this explicit relationship, never inferred.
    broker_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="company", foreign_keys="User.company_id"
    )
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
