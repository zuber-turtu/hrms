
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company
from app.dependencies import require_auth, RoleChecker
from app.schemas.company import CompanyProfileOut, CompanyProfileUpdate
from app.utils.geofence import get_or_create_company

router = APIRouter(prefix="/company", tags=["Company"])
allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])


@router.get("/profile", response_model=CompanyProfileOut)
async def get_company_profile(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    company = get_or_create_company(db)
    return company


@router.put("/profile", response_model=CompanyProfileOut)
async def update_company_profile(
    payload: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = get_or_create_company(db)

    update_dict = payload.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field in ["cin", "gstin", "pan", "currency_code"] and isinstance(value, str):
            value = value.strip().upper() if value.strip() else None
        elif isinstance(value, str):
            value = value.strip()
        setattr(company, field, value)

    db.commit()
    db.refresh(company)
    return company
