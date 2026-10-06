from typing import Optional, List
import datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department
from app.models.payroll import Payslip
from app.models.company import Company
from app.models.audit import AuditLog
from app.utils.timezone import get_ist_today
from app.dependencies import require_auth, RoleChecker

from app.services.payroll_calculator import (
    generate_draft_payslip,
    bulk_generate_payslips,
    bulk_update_payslip_status,
    bulk_delete_draft_payslips,
    bulk_generate_payslips_zip,
)
from app.services.pdf_generator import generate_payslip_pdf
from app.services.formatters import number_to_words, get_month_name, mask_account_number, get_payslip_pdf_filename
from app.templates_config import templates
from app.utils.flash import flash_redirect

router = APIRouter(prefix="/payroll")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_payroll(
    request: Request,
    msg: Optional[str] = None,
    msg_type: Optional[str] = "success",
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
        payslips = (
            db.query(Payslip)
            .filter(
                Payslip.employee_id == current_user.id,
                Payslip.status.in_(["finalized", "paid"])
            )
            .order_by(Payslip.year.desc(), Payslip.month.desc())
            .all()
        )
    else:
        payslips = db.query(Payslip).order_by(Payslip.year.desc(), Payslip.month.desc()).all()


    employees = db.query(Employee).filter(Employee.is_active == True, Employee.role != "super_admin").all()
    departments = db.query(Department).all()

    today = get_ist_today()
    current_month = today.month
    current_year = today.year
    
    db_years = set()
    for p in payslips:
        if p and p.year is not None:
            try:
                db_years.add(int(p.year))
            except (ValueError, TypeError):
                pass
    db_years.update(range(current_year - 2, current_year + 3))
    available_years = sorted(list(db_years), reverse=True)

    return templates.TemplateResponse(
        request,
        "payroll/list.html",
        {
            "user": current_user,
            "payslips": payslips,
            "employees": employees,
            "departments": departments,
            "current_month": current_month,
            "current_year": current_year,
            "available_years": available_years,
            "flash_msg": msg,
            "flash_msg_type": msg_type,
        },
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
    target_emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not target_emp:
        return flash_redirect(url="/payroll", message="Selected employee not found", category="error")

    if target_emp.role == "super_admin":
        return flash_redirect(url="/payroll", message="Super Admin is an executive officer and exempt from payroll generation.", category="error")

    # Check if already exists
    existing = db.query(Payslip).filter(
        Payslip.employee_id == employee_id,
        Payslip.month == month,
        Payslip.year == year,
    ).first()

    if existing:
        return flash_redirect(url=f"/payroll/{existing.id}/edit", message=f"A payslip for {target_emp.name} already exists for {month}/{year}.", category="info")

    draft_data = generate_draft_payslip(db, employee_id, month, year)
    if draft_data:
        payslip = Payslip(**draft_data)
        db.add(payslip)
        db.commit()
        db.refresh(payslip)
        return flash_redirect(url=f"/payroll/{payslip.id}/edit", message=f"Draft payslip for {target_emp.name} generated successfully.", category="success")

    return flash_redirect(url="/payroll", message=f"Could not compute draft payslip for {target_emp.name}.", category="error")


@router.post("/bulk-generate")
async def bulk_generate(
    request: Request,
    month: int = Form(...),
    year: int = Form(...),
    department_id: Optional[str] = Form(None),
    overwrite_drafts: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    dept_id_int = int(department_id) if department_id and department_id.strip() and department_id != "all" else None
    is_overwrite = bool(overwrite_drafts and overwrite_drafts.lower() in ["true", "1", "on", "yes"])

    result = bulk_generate_payslips(
        db=db,
        month=month,
        year=year,
        department_id=dept_id_int,
        overwrite_drafts=is_overwrite,
        actor=current_user,
    )

    msg = (
        f"Bulk payroll generated for {month}/{year}: {result['created']} draft(s) created, "
        f"{result['updated']} draft(s) recalculated, {result['skipped_existing']} skipped, "
        f"{result['skipped_finalized']} finalized/paid protected."
    )
    return flash_redirect(url="/payroll", message=msg, category="success")


@router.post("/bulk-status")
async def bulk_status_action(
    request: Request,
    payslip_ids: str = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    id_list = [int(x.strip()) for x in payslip_ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return flash_redirect(url="/payroll", message="No payslips selected", category="error")

    if action not in ["draft", "finalized", "paid"]:
        return flash_redirect(url="/payroll", message="Invalid status selected", category="error")

    res = bulk_update_payslip_status(db, id_list, action, actor=current_user)
    msg = f"Successfully updated {res['updated_count']} payslip(s) to '{action.title()}' status."
    return flash_redirect(url="/payroll", message=msg, category="success")


@router.post("/bulk-delete")
async def bulk_delete_action(
    request: Request,
    payslip_ids: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    id_list = [int(x.strip()) for x in payslip_ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return flash_redirect(url="/payroll", message="No payslips selected", category="error")

    res = bulk_delete_draft_payslips(db, id_list, actor=current_user)
    msg = f"Deleted {res['deleted_count']} draft payslip(s)."
    if res["skipped_locked_count"] > 0:
        msg += f" (Protected {res['skipped_locked_count']} finalized/paid records from deletion)"
    return flash_redirect(url="/payroll", message=msg, category="info")


@router.get("/bulk-export-zip")
@router.post("/bulk-export-zip")
async def bulk_export_zip(
    request: Request,
    ids: Optional[str] = Query(None),
    payslip_ids: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    raw_ids = payslip_ids or ids or ""
    id_list = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
    if not id_list:
        all_payslips = db.query(Payslip.id).all()
        id_list = [p[0] for p in all_payslips]

    if not id_list:
        return flash_redirect(url="/payroll", message="No payslips available to export", category="error")

    zip_stream = bulk_generate_payslips_zip(db, id_list)
    timestamp = datetime.date.today().strftime("%Y%m%d")
    headers = {
        "Content-Disposition": f'attachment; filename="payslips_batch_{timestamp}.zip"'
    }
    return Response(
        content=zip_stream.getvalue(),
        media_type="application/zip",
        headers=headers,
    )


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
    generated_on: Optional[str] = Form(None),
    basic: float = Form(0.0),
    hra: float = Form(0.0),
    allowances: float = Form(0.0),
    bonus: float = Form(0.0),
    pf: float = Form(0.0),
    tax: float = Form(0.0),
    other_deductions: float = Form(0.0),
    status: str = Form("draft"),
    payable_days: int = Form(22),
    days_worked: float = Form(22.0),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if payslip:
        old_val = f"Date: {payslip.generated_on}, Basic: {payslip.basic}, Days: {payslip.days_worked}/{payslip.payable_days}, Net: {payslip.net_salary}, Status: {payslip.status}"

        if generated_on and generated_on.strip():
            try:
                payslip.generated_on = datetime.datetime.strptime(generated_on.strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

        payslip.payable_days = payable_days
        payslip.days_worked = days_worked
        payslip.basic = basic
        payslip.hra = hra
        payslip.allowances = allowances
        payslip.bonus = bonus
        payslip.pf = pf
        payslip.tax = tax
        payslip.other_deductions = other_deductions
        payslip.net_salary = (basic + hra + allowances + bonus) - (pf + tax + other_deductions)
        payslip.status = status

        new_val = f"Date: {payslip.generated_on}, Basic: {payslip.basic}, Days: {payslip.days_worked}/{payslip.payable_days}, Net: {payslip.net_salary}, Status: {payslip.status}"

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


@router.get("/{payslip_id}/view", response_class=HTMLResponse)
async def view_payslip(
    payslip_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        raise HTTPException(status_code=404, detail="Payslip not found")

    if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"] and not getattr(current_user, "is_super_admin", False):
        if payslip.employee_id != current_user.id or payslip.status == "draft":
            raise HTTPException(status_code=403, detail="Unauthorized to view this payslip (still in draft review)")

    company = db.query(Company).first()
    currency = company.currency_symbol if company and company.currency_symbol else "$"
    month_name = get_month_name(payslip.month)
    amount_in_words = number_to_words(payslip.net_salary, "Dollars" if currency == "$" else "Rupees")
    masked_acc = mask_account_number(
        payslip.employee.bank_account.account_number if payslip.employee and payslip.employee.bank_account else ""
    )
    pdf_filename = get_payslip_pdf_filename(payslip)

    return templates.TemplateResponse(
        request=request,
        name="payroll/view_payslip.html",
        context={
            "user": current_user,
            "payslip": payslip,
            "company": company,
            "currency": currency,
            "month_name": month_name,
            "amount_in_words": amount_in_words,
            "masked_account": masked_acc,
            "pdf_filename": pdf_filename,
        },
    )


@router.get("/{payslip_id}/pdf")
async def download_payslip_pdf(
    payslip_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        return Response(status_code=404)

    if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"] and not getattr(current_user, "is_super_admin", False):
        if payslip.employee_id != current_user.id or payslip.status == "draft":
            return Response(status_code=403)

    company = db.query(Company).first()
    pdf_buffer = generate_payslip_pdf(payslip, company, payslip.employee)
    filename = get_payslip_pdf_filename(payslip)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return Response(content=pdf_buffer.read(), media_type="application/pdf", headers=headers)


