from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company
from app.dependencies import require_auth, RoleChecker
from app.templates_config import templates

router = APIRouter(prefix="/company")

allow_hr_admin = RoleChecker(["admin", "hr_admin"])


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
    name: str = Form("Acme Corp"),
    tagline: Optional[str] = Form(None),
    address: str = Form(""),
    support_email: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    logo_url: Optional[str] = Form(None),
    currency_symbol: str = Form("$"),
    currency_code: str = Form("USD"),
    working_days_per_month: int = Form(22),
    standard_hours_per_day: float = Form(8.0),
    half_day_threshold_hours: float = Form(4.0),
    cin: Optional[str] = Form(None),
    gstin: Optional[str] = Form(None),
    pan: Optional[str] = Form(None),
    office_latitude: Optional[str] = Form(None),
    office_longitude: Optional[str] = Form(None),
    geofence_radius_meters: int = Form(200),
    geofence_enabled: bool = Form(False),
    geofence_strict_mode: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = db.query(Company).first()
    if not company:
        company = Company()
        db.add(company)

    company.name = name.strip() if name else "Acme Corp"
    company.tagline = tagline.strip() if tagline and tagline.strip() else None
    company.address = address.strip() if address else ""
    company.support_email = support_email.strip() if support_email and support_email.strip() else None
    company.website = website.strip() if website and website.strip() else None
    if logo_url is not None:
        company.logo_url = logo_url.strip() if logo_url.strip() else None
    company.currency_symbol = currency_symbol.strip() if currency_symbol else "$"
    company.currency_code = currency_code.strip().upper() if currency_code else "USD"
    company.working_days_per_month = working_days_per_month
    company.standard_hours_per_day = standard_hours_per_day
    company.half_day_threshold_hours = half_day_threshold_hours
    company.cin = cin.strip().upper() if cin and cin.strip() else None
    company.gstin = gstin.strip().upper() if gstin and gstin.strip() else None
    company.pan = pan.strip().upper() if pan and pan.strip() else None

    # Geofence parameters
    if office_latitude and office_latitude.strip():
        try:
            company.office_latitude = float(office_latitude.strip())
        except ValueError:
            company.office_latitude = None
    else:
        company.office_latitude = None

    if office_longitude and office_longitude.strip():
        try:
            company.office_longitude = float(office_longitude.strip())
        except ValueError:
            company.office_longitude = None
    else:
        company.office_longitude = None

    company.geofence_radius_meters = max(10, int(geofence_radius_meters))
    company.geofence_enabled = geofence_enabled
    company.geofence_strict_mode = geofence_strict_mode

    db.commit()

    return RedirectResponse(url="/company/profile?success=Company+and+geofence+settings+saved+successfully", status_code=302)
