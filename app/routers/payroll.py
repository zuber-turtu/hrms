from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import datetime

from app.database import get_db
from app.models.employee import Employee
from app.models.payroll import Payslip
from app.models.company import Company
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.services.payroll_calculator import generate_draft_payslip
from app.services.pdf_generator import generate_payslip_pdf

router = APIRouter(prefix="/payroll")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["super_admin", "hr_admin"])


@router.get("/", response_class=HTMLResponse)
async def list_payroll(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role == "employee":
        payslips = db.query(Payslip).filter(Payslip.employee_id == current_user.id).all()
    else:
        payslips = db.query(Payslip).all()

    employees = db.query(Employee).all()

    return templates.TemplateResponse(
        request,
        "payroll/list.html",
        {"user": current_user, "payslips": payslips, "employees": employees},
    )


@router.post("/generate-draft")
async def generate_draft(
    request: Request,
    employee_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    # Check if already exists
    existing = db.query(Payslip).filter(
        Payslip.employee_id == employee_id,
        Payslip.month == month,
        Payslip.year == year,
    ).first()

    if existing:
        return RedirectResponse(url=f"/payroll/{existing.id}/edit", status_code=302)

    draft_data = generate_draft_payslip(db, employee_id, month, year)
    if draft_data:
        payslip = Payslip(**draft_data)
        db.add(payslip)
        db.commit()
        db.refresh(payslip)
        return RedirectResponse(url=f"/payroll/{payslip.id}/edit", status_code=302)

    return RedirectResponse(url="/payroll", status_code=302)


@router.get("/{payslip_id}/edit", response_class=HTMLResponse)
async def edit_payslip_form(
    payslip_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    return templates.TemplateResponse(
        request, "payroll/edit_payslip.html", {"user": current_user, "payslip": payslip}
    )


@router.post("/{payslip_id}/edit")
async def update_payslip(
    payslip_id: int,
    request: Request,
    basic: float = Form(...),
    hra: float = Form(...),
    allowances: float = Form(...),
    bonus: float = Form(...),
    pf: float = Form(...),
    tax: float = Form(...),
    other_deductions: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if payslip:
        old_val = f"Basic: {payslip.basic}, Net: {payslip.net_salary}"

        payslip.basic = basic
        payslip.hra = hra
        payslip.allowances = allowances
        payslip.bonus = bonus
        payslip.pf = pf
        payslip.tax = tax
        payslip.other_deductions = other_deductions
        payslip.net_salary = (basic + hra + allowances + bonus) - (pf + tax + other_deductions)
        payslip.status = status

        new_val = f"Basic: {payslip.basic}, Net: {payslip.net_salary}"

        audit = AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="PAYSLIP_EDIT",
            entity="Payslip",
            entity_id=payslip.id,
            old_value=old_val,
            new_value=new_val,
        )
        db.add(audit)
        db.commit()

    return RedirectResponse(url="/payroll", status_code=302)


@router.get("/{payslip_id}/pdf")
async def download_payslip_pdf(
    payslip_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        return Response(status_code=404)

    if current_user.role == "employee" and payslip.employee_id != current_user.id:
        return Response(status_code=403)

    company = db.query(Company).first()
    pdf_buffer = generate_payslip_pdf(payslip, company, payslip.employee)

    headers = {
        "Content-Disposition": f'attachment; filename="payslip_{payslip.month}_{payslip.year}.pdf"'
    }
    return Response(content=pdf_buffer.read(), media_type="application/pdf", headers=headers)
