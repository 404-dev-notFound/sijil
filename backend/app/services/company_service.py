from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import User
from app.repositories.company_repository import CompanyRepository
from app.utils.exceptions import NotFoundError


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self._companies = CompanyRepository(session)

    async def get_company_for_user(self, user: User) -> Company:
        company = await self._companies.get_by_id(user.company_id)
        if company is None:
            raise NotFoundError("Company not found.")
        return company
