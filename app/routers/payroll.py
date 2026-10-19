from typing import Optional, List
import datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department
from app.models.payroll import Payslip
from app.models.company import Company
from app.models.audit import AuditLog
from app.utils.timezone import get_ist_today
from app.dependencies import require_auth, RoleChecker
from app.utils.permissions import can_manage_employee

from app.services.payroll_calculator import (
    generate_draft_payslip,
    bulk_generate_payslips,
    bulk_update_payslip_status,
    bulk_delete_draft_payslips,
    bulk_generate_payslips_zip,
    freeze_payslip_bank_snapshot,
)
from app.services.pdf_generator import generate_payslip_pdf
from app.services.formatters import number_to_words, get_month_name, mask_account_number, get_payslip_pdf_filename
from app.templates_config import templates
from app.utils.flash import flash_redirect
from app.services.excel_exporter import export_payroll_excel
from app.services.email_service import send_payslip_email

router = APIRouter(prefix="/payroll")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_payroll(
    request: Request,
    page: Optional[int] = 1,
    page_size: Optional[int] = 25,
    month: Optional[int] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    dept_id: Optional[int] = None,
    q: Optional[str] = None,
    msg: Optional[str] = None,
    msg_type: Optional[str] = "success",
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    from sqlalchemy import or_, func, cast, String
    from app.utils.pagination import paginate_query

    query = db.query(Payslip).join(Employee, Payslip.employee_id == Employee.id)

    if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
        query = query.filter(
            Payslip.employee_id == current_user.id,
            Payslip.status.in_(["finalized", "paid"])
        )
    else:
        # Department filter
        if dept_id and dept_id > 0:
            query = query.filter(Employee.department_id == dept_id)

    # Search filter
    if q and q.strip():
        search_term = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                Employee.name.ilike(search_term),
                Employee.email.ilike(search_term),
                cast(Payslip.id, String).ilike(search_term),
            )
        )

    # Month and Year filter
    if month and month > 0:
        query = query.filter(Payslip.month == month)
    if year and year > 0:
        query = query.filter(Payslip.year == year)

    # Status filter
    if status and status.strip() and status.lower() != "all":
        query = query.filter(Payslip.status == status.strip().lower())

    query = query.order_by(Payslip.year.desc(), Payslip.month.desc(), Employee.name.asc())

    page_data = paginate_query(query, page=page, page_size=page_size)

    employees = (
        db.query(Employee)
        .options(joinedload(Employee.department))
        .filter(Employee.is_active == True, Employee.role != "super_admin")
        .order_by(Employee.name.asc())
        .limit(10)
        .all()
    )
    departments = db.query(Department).all()

    today = get_ist_today()
    current_month = today.month
    current_year = today.year
    
    available_years = sorted(list(range(current_year - 3, current_year + 3)), reverse=True)

    context = {
        "request": request,
        "user": current_user,
        "page_data": page_data,
        "payslips": page_data.items,
        "employees": employees,
        "departments": departments,
        "current_month": month if month is not None else 0,
        "current_year": year if year is not None else current_year,
        "available_years": available_years,
        "selected_status": status or "all",
        "selected_dept": dept_id or 0,
        "q": q or "",
        "flash_msg": msg,
        "flash_msg_type": msg_type,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "payroll/partials/_table.html",
            context,
        )

    return templates.TemplateResponse(
        request,
        "payroll/list.html",
        context,
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

    if not can_manage_employee(current_user, target_emp):
        return flash_redirect(url="/payroll", message="Operation not permitted: You cannot generate payroll for an account of higher or equal role.", category="error")

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


@router.post("/{payslip_id}/send-email")
async def send_single_payslip_email_action(
    payslip_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Emails the finalized or paid payslip statement with PDF attachment to an individual employee."""
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        return flash_redirect(url="/payroll", message="Payslip record not found", category="error")

    if not can_manage_employee(current_user, payslip.employee):
        return flash_redirect(url="/payroll", message="Operation not permitted: You cannot send payslips for an account of higher or equal role.", category="error")

    if payslip.status not in ["finalized", "paid"]:
        return flash_redirect(url="/payroll", message="Cannot email draft payslips. Please finalize or mark paid first.", category="error")

    if not payslip.employee or not payslip.employee.email:
        emp_name = payslip.employee.name if payslip.employee else "Employee"
        return flash_redirect(url="/payroll", message=f"{emp_name} does not have a registered email address.", category="error")

    company = db.query(Company).first()
    month_name = get_month_name(payslip.month)

    try:
        sent = send_payslip_email(payslip, employee=payslip.employee, company=company)
        if sent:
            payslip.emailed_at = datetime.datetime.now()
            audit = AuditLog(
                actor_id=current_user.id,
                actor_email=current_user.email,
                action="PAYSLIP_EMAIL_SENT",
                entity="Payslip",
                entity_id=payslip.id,
                new_value=f"Emailed payslip for {month_name} {payslip.year} to {payslip.employee.email}",
            )
            db.add(audit)
            db.commit()
            return flash_redirect(
                url="/payroll",
                message=f"Official payslip for {payslip.employee.name} ({month_name} {payslip.year}) was successfully emailed to {payslip.employee.email}.",
                category="success",
            )
        else:
            return flash_redirect(
                url="/payroll",
                message=f"Failed to send email to {payslip.employee.email}. Please verify SMTP configuration.",
                category="error",
            )
    except Exception as e:
        return flash_redirect(url="/payroll", message=f"Error sending payslip email: {str(e)}", category="error")


@router.post("/bulk-send-email")
async def bulk_send_email_action(
    request: Request,
    payslip_ids: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Dispatches payslip emails with attached PDFs for all selected finalized or paid records."""
    id_list = [int(x.strip()) for x in payslip_ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return flash_redirect(url="/payroll", message="No payslips selected for email dispatch", category="error")

    payslips = db.query(Payslip).filter(Payslip.id.in_(id_list)).all()
    if not payslips:
        return flash_redirect(url="/payroll", message="No matching payslips found", category="error")

    company = db.query(Company).first()
    sent_count = 0
    failed_count = 0
    draft_skipped = 0
    no_email_skipped = 0

    for p in payslips:
        if p.status not in ["finalized", "paid"]:
            draft_skipped += 1
            continue

        if not p.employee or not p.employee.email:
            no_email_skipped += 1
            continue

        try:
            ok = send_payslip_email(p, employee=p.employee, company=company)
            if ok:
                sent_count += 1
                p.emailed_at = datetime.datetime.now()
                audit = AuditLog(
                    actor_id=current_user.id,
                    actor_email=current_user.email,
                    action="PAYSLIP_EMAIL_SENT",
                    entity="Payslip",
                    entity_id=p.id,
                    new_value=f"Bulk emailed {get_month_name(p.month)} {p.year} payslip to {p.employee.email}",
                )
                db.add(audit)
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    if sent_count > 0:
        db.commit()

    parts = [f"Successfully emailed {sent_count} payslip(s) to employees."]
    if failed_count > 0:
        parts.append(f"({failed_count} delivery failed)")
    if draft_skipped > 0:
        parts.append(f"(Protected {draft_skipped} unfinalized draft(s) from email dispatch)")
    if no_email_skipped > 0:
        parts.append(f"(Skipped {no_email_skipped} employee(s) without email addresses)")

    category = "success" if sent_count > 0 else ("error" if failed_count > 0 else "info")
    return flash_redirect(url="/payroll", message=" ".join(parts), category=category)


@router.post("/department-send-email")
async def department_send_email_action(
    request: Request,
    month: int = Form(...),
    year: int = Form(...),
    department_id: Optional[str] = Form("all"),
    status_filter: Optional[str] = Form("all"),
    skip_already_emailed: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Dispatches payslip emails across a department or entire workforce for a selected month/year."""
    query = db.query(Payslip).join(Employee, Payslip.employee_id == Employee.id)
    query = query.filter(Payslip.month == month, Payslip.year == year)

    # Strictly protect drafts - only finalized or paid
    if status_filter == "finalized":
        query = query.filter(Payslip.status == "finalized")
    elif status_filter == "paid":
        query = query.filter(Payslip.status == "paid")
    else:
        query = query.filter(Payslip.status.in_(["finalized", "paid"]))

    dept_id_int = int(department_id) if department_id and department_id.strip() and department_id != "all" else None
    if dept_id_int:
        query = query.filter(Employee.department_id == dept_id_int)

    is_skip = bool(skip_already_emailed and skip_already_emailed.lower() in ["true", "1", "on", "yes"])
    if is_skip:
        query = query.filter(Payslip.emailed_at == None)

    eligible_payslips = query.all()
    if not eligible_payslips:
        period_str = f"{get_month_name(month)} {year}"
        reason = "all matching records have already been emailed" if is_skip else "no finalized or paid records exist for this period"
        return flash_redirect(
            url="/payroll",
            message=f"No eligible payslips found to email for {period_str} ({reason}).",
            category="info",
        )

    company = db.query(Company).first()
    sent_count = 0
    failed_count = 0
    no_email_count = 0

    for p in eligible_payslips:
        if not p.employee or not p.employee.email:
            no_email_count += 1
            continue

        try:
            ok = send_payslip_email(p, employee=p.employee, company=company)
            if ok:
                sent_count += 1
                p.emailed_at = datetime.datetime.now()
                audit = AuditLog(
                    actor_id=current_user.id,
                    actor_email=current_user.email,
                    action="PAYSLIP_EMAIL_SENT",
                    entity="Payslip",
                    entity_id=p.id,
                    new_value=f"Department/Batch emailed {get_month_name(p.month)} {p.year} payslip to {p.employee.email}",
                )
                db.add(audit)
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    if sent_count > 0:
        db.commit()

    dept_label = "entire workforce"
    if dept_id_int:
        target_dept = db.query(Department).filter(Department.id == dept_id_int).first()
        if target_dept:
            dept_label = f"'{target_dept.name}' department"

    msg = f"Dispatched {sent_count} payslip email(s) with PDF statements to {dept_label} for {get_month_name(month)} {year}."
    if failed_count > 0:
        msg += f" ({failed_count} delivery failed)"
    if no_email_count > 0:
        msg += f" (Skipped {no_email_count} without registered emails)"

    category = "success" if sent_count > 0 else "error"
    return flash_redirect(url="/payroll", message=msg, category=category)


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


@router.get("/export-excel")
async def export_payroll_spreadsheet(
    month: Optional[int] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    dept_id: Optional[int] = None,
    q: Optional[str] = None,
    ids: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Exports payroll and banking register to styled Excel sheet matching active filters."""
    from sqlalchemy import or_, cast, String
    query = db.query(Payslip).join(Employee, Payslip.employee_id == Employee.id)

    if ids and ids.strip():
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.filter(Payslip.id.in_(id_list))
    else:
        if dept_id and dept_id > 0:
            query = query.filter(Employee.department_id == dept_id)

        if q and q.strip():
            search_term = f"%{q.strip().lower()}%"
            query = query.filter(
                or_(
                    Employee.name.ilike(search_term),
                    Employee.email.ilike(search_term),
                    cast(Payslip.id, String).ilike(search_term),
                )
            )

        if month and month > 0:
            query = query.filter(Payslip.month == month)
        if year and year > 0:
            query = query.filter(Payslip.year == year)

        if status and status.strip() and status.lower() != "all":
            query = query.filter(Payslip.status == status.strip().lower())

    payslips = query.order_by(Payslip.year.desc(), Payslip.month.desc(), Employee.name.asc()).all()
    company = db.query(Company).first()
    return export_payroll_excel(payslips, company, month=month, year=year)


@router.get("/{payslip_id}/edit", response_class=HTMLResponse)
async def edit_payslip_form(
    payslip_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        return flash_redirect(url="/payroll", message="Payslip record not found", category="error")
    if not can_manage_employee(current_user, payslip.employee):
        return flash_redirect(url="/payroll", message="Operation not permitted: You cannot edit payslip for an account of higher or equal role.", category="error")

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
    if not payslip:
        return flash_redirect(url="/payroll", message="Payslip record not found", category="error")
    if not can_manage_employee(current_user, payslip.employee):
        return flash_redirect(url="/payroll", message="Operation not permitted: You cannot modify payslip for an account of higher or equal role.", category="error")

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
        if status in ["finalized", "paid"]:
            freeze_payslip_bank_snapshot(payslip)
        elif status == "draft":
            payslip.bank_name = None
            payslip.account_number = None
            payslip.ifsc_code = None

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

    if current_user.id != payslip.employee_id:
        if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"] and not getattr(current_user, "is_super_admin", False):
            raise HTTPException(status_code=403, detail="Unauthorized to view this payslip")
        if not can_manage_employee(current_user, payslip.employee) and current_user.role not in ["super_admin", "admin"]:
            raise HTTPException(status_code=403, detail="Unauthorized to view payslip of higher or equal corporate tier")
    elif payslip.status == "draft":
        raise HTTPException(status_code=403, detail="Unauthorized to view this payslip (still in draft review)")

    company = db.query(Company).first()
    currency = company.currency_symbol if company and company.currency_symbol else "$"
    month_name = get_month_name(payslip.month)
    amount_in_words = number_to_words(payslip.net_salary, "Dollars" if currency == "$" else "Rupees")
    raw_acc = payslip.account_number or (
        payslip.employee.bank_account.account_number if payslip.employee and payslip.employee.bank_account else ""
    )
    masked_acc = mask_account_number(raw_acc)
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

    if current_user.id != payslip.employee_id:
        if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"] and not getattr(current_user, "is_super_admin", False):
            return Response(status_code=403)
        if not can_manage_employee(current_user, payslip.employee) and current_user.role not in ["super_admin", "admin"]:
            return Response(status_code=403)
    elif payslip.status == "draft":
        return Response(status_code=403)

    company = db.query(Company).first()
    pdf_buffer = generate_payslip_pdf(payslip, company, payslip.employee)
    filename = get_payslip_pdf_filename(payslip)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return Response(content=pdf_buffer.read(), media_type="application/pdf", headers=headers)


