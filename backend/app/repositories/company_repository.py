import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, company: Company) -> Company:
        self._session.add(company)
        await self._session.flush()
        return company

    async def get_by_id(self, company_id: uuid.UUID) -> Company | None:
        return await self._session.get(Company, company_id)

    async def get_by_trade_license_number(self, trade_license_number: str) -> Company | None:
        stmt = select(Company).where(Company.trade_license_number == trade_license_number)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_managed_companies(self, broker_company_id: uuid.UUID) -> list[Company]:
        stmt = select(Company).where(Company.broker_company_id == broker_company_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
