from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company
from app.dependencies import require_auth, RoleChecker
from app.schemas.company import CompanyProfileOut, CompanyProfileUpdate

router = APIRouter(prefix="/company", tags=["Company"])
allow_hr_admin = RoleChecker(["admin", "hr_admin"])


def _get_or_create_company(db: Session) -> Company:
    company = db.query(Company).first()
    if not company:
        company = Company(
            name="Acme Corp",
            address="123 Enterprise Way",
            currency_symbol="$",
            working_days_per_month=22,
        )
        db.add(company)
        db.commit()
        db.refresh(company)
    return company


@router.get("/profile", response_model=CompanyProfileOut)
async def get_company_profile(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    company = _get_or_create_company(db)
    return company


@router.put("/profile", response_model=CompanyProfileOut)
async def update_company_profile(
    payload: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = _get_or_create_company(db)

    if payload.name is not None:
        company.name = payload.name
    if payload.address is not None:
        company.address = payload.address
    if payload.currency_symbol is not None:
        company.currency_symbol = payload.currency_symbol
    if payload.working_days_per_month is not None:
        company.working_days_per_month = payload.working_days_per_month

    db.commit()
    db.refresh(company)
    return company
