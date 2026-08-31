from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company
from app.dependencies import require_auth, RoleChecker

router = APIRouter(prefix="/company")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["super_admin", "hr_admin"])


@router.get("/profile", response_class=HTMLResponse)
async def company_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = db.query(Company).first()
    if not company:
        company = Company()
        db.add(company)
        db.commit()
        db.refresh(company)

    return templates.TemplateResponse(
        request, "company/profile.html", {"user": current_user, "company": company}
    )


@router.post("/profile")
async def update_company_profile(
    request: Request,
    name: str = Form(...),
    address: str = Form(...),
    currency_symbol: str = Form(...),
    working_days_per_month: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = db.query(Company).first()
    if not company:
        company = Company()
        db.add(company)

    company.name = name
    company.address = address
    company.currency_symbol = currency_symbol
    company.working_days_per_month = working_days_per_month
    db.commit()

    return RedirectResponse(url="/company/profile", status_code=302)
