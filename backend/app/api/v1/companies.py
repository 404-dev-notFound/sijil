from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.company import CompanyOut
from app.services.company_service import CompanyService

router = APIRouter()


@router.get("/me", response_model=CompanyOut)
async def get_my_company(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompanyOut:
    company = await CompanyService(db).get_company_for_user(user)
    return CompanyOut.model_validate(company)
