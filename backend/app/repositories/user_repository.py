import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_in_company(self, user_id: uuid.UUID, company_id: uuid.UUID) -> User | None:
        # Mandatory company_id scope, even for a single-row lookup by primary key —
        # architecture doc Section 14: no query method exists without a tenant scope.
        stmt = select(User).where(User.id == user_id, User.company_id == company_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: uuid.UUID) -> list[User]:
        stmt = select(User).where(User.company_id == company_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
