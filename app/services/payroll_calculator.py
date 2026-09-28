import io
import zipfile
import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import extract

from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.company import Company
from app.models.payroll import Payslip
from app.models.audit import AuditLog
from app.services.pdf_generator import generate_payslip_pdf
from app.services.formatters import get_payslip_pdf_filename, get_month_name
from app.config import settings
from app.utils.timezone import get_ist_today


def calculate_pro_rata(amount: float, days_worked: float, payable_days: int) -> float:
    if payable_days == 0:
        return 0.0
    return round(amount * (days_worked / payable_days), 2)


def generate_draft_payslip(db: Session, employee_id: int, month: int, year: int) -> Optional[dict]:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return None

    company = db.query(Company).first()
    working_days = company.working_days_per_month if company and company.working_days_per_month else settings.COMPANY_WORKING_DAYS_PER_MONTH
    payable_days = working_days

    # Calculate days worked based on attendance
    attendances = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        extract('month', Attendance.date) == month,
        extract('year', Attendance.date) == year
    ).all()

    # Count distinct days attended
    distinct_dates = set([a.date for a in attendances if a.date])
    days_worked = float(len(distinct_dates))

    # Cap days worked at payable days
    days_worked = min(days_worked, float(payable_days))

    base_salary = employee.base_salary or 0.0
    hra = employee.hra or 0.0
    custom_allowances = employee.custom_allowances or 0.0
    pf_deduction = employee.pf_deduction or 0.0
    tax_deduction = employee.tax_deduction or 0.0

    # Pro rata logic
    basic = calculate_pro_rata(base_salary, days_worked, payable_days)
    hra_val = calculate_pro_rata(hra, days_worked, payable_days)
    allowances = calculate_pro_rata(custom_allowances, days_worked, payable_days)

    pf = calculate_pro_rata(pf_deduction, days_worked, payable_days)
    tax = calculate_pro_rata(tax_deduction, days_worked, payable_days)

    net_salary = round(basic + hra_val + allowances - pf - tax, 2)

    return {
        "employee_id": employee.id,
        "month": month,
        "year": year,
        "payable_days": payable_days,
        "days_worked": days_worked,
        "basic": basic,
        "hra": hra_val,
        "allowances": allowances,
        "bonus": 0.0,
        "pf": pf,
        "tax": tax,
        "other_deductions": 0.0,
        "net_salary": net_salary,
        "status": "draft"
    }


def bulk_generate_payslips(
    db: Session,
    month: int,
    year: int,
    department_id: Optional[int] = None,
    overwrite_drafts: bool = False,
    actor: Optional[Employee] = None,
) -> Dict[str, Any]:
    """
    Generates draft payslips in bulk for eligible active employees.
    Safe & Idempotent:
      - Never touches or overwrites 'finalized' or 'paid' payslips.
      - If overwrite_drafts is True, recalculates unfinalized 'draft' payslips.
      - If overwrite_drafts is False, skips employees with existing 'draft'.
      - Inserts new 'draft' payslips for employees who don't have one yet.
    """
    query = db.query(Employee).filter(Employee.is_active == True, Employee.role != "admin")
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    employees = query.all()

    created_count = 0
    updated_count = 0
    skipped_existing_count = 0
    skipped_finalized_count = 0
    errors = []

    for emp in employees:
        try:
            existing = db.query(Payslip).filter(
                Payslip.employee_id == emp.id,
                Payslip.month == month,
                Payslip.year == year,
            ).first()

            if existing:
                if existing.status in ["finalized", "paid"]:
                    skipped_finalized_count += 1
                    continue
                elif existing.status == "draft":
                    if overwrite_drafts:
                        draft_data = generate_draft_payslip(db, emp.id, month, year)
                        if draft_data:
                            existing.payable_days = draft_data["payable_days"]
                            existing.days_worked = draft_data["days_worked"]
                            existing.basic = draft_data["basic"]
                            existing.hra = draft_data["hra"]
                            existing.allowances = draft_data["allowances"]
                            existing.pf = draft_data["pf"]
                            existing.tax = draft_data["tax"]
                            existing.net_salary = draft_data["net_salary"]
                            existing.generated_on = get_ist_today()
                            updated_count += 1
                    else:
                        skipped_existing_count += 1
                    continue

            draft_data = generate_draft_payslip(db, emp.id, month, year)
            if draft_data:
                payslip = Payslip(**draft_data)
                db.add(payslip)
                created_count += 1
            else:
                errors.append(f"Failed to generate draft calculation for employee {emp.name} (ID: {emp.id})")
        except Exception as e:
            errors.append(f"Error processing employee {emp.name}: {str(e)}")

    db.commit()

    if actor:
        audit = AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action="BULK_PAYROLL_GENERATE",
            entity="Payslip",
            old_value=None,
            new_value=(
                f"Bulk Payroll ({month}/{year}) executed. Created: {created_count}, "
                f"Updated: {updated_count}, Skipped Existing: {skipped_existing_count}, "
                f"Skipped Finalized/Paid: {skipped_finalized_count}, Errors: {len(errors)}"
            ),
        )
        db.add(audit)
        db.commit()

    return {
        "total_eligible": len(employees),
        "created": created_count,
        "updated": updated_count,
        "skipped_existing": skipped_existing_count,
        "skipped_finalized": skipped_finalized_count,
        "month": month,
        "year": year,
        "department_id": department_id,
        "errors": errors,
    }


def bulk_update_payslip_status(
    db: Session,
    payslip_ids: List[int],
    new_status: str,
    actor: Optional[Employee] = None,
) -> Dict[str, Any]:
    """
    Updates the status of multiple payslips at once.
    Allowed target statuses: 'draft', 'finalized', 'paid'.
    """
    if new_status not in ["draft", "finalized", "paid"]:
        raise ValueError(f"Invalid status '{new_status}'. Allowed: draft, finalized, paid.")

    payslips = db.query(Payslip).filter(Payslip.id.in_(payslip_ids)).all()
    updated_count = 0

    for p in payslips:
        p.status = new_status
        updated_count += 1

    db.commit()

    if actor and updated_count > 0:
        audit = AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action="BULK_PAYSLIP_STATUS_UPDATE",
            entity="Payslip",
            old_value=None,
            new_value=f"Batch updated {updated_count} payslips to status '{new_status}' (IDs: {payslip_ids[:20]})",
        )
        db.add(audit)
        db.commit()

    return {
        "updated_count": updated_count,
        "status": new_status,
    }


def bulk_delete_draft_payslips(
    db: Session,
    payslip_ids: List[int],
    actor: Optional[Employee] = None,
) -> Dict[str, Any]:
    """
    Deletes payslips in bulk.
    Safety rule: ONLY deletes payslips in 'draft' status. Never deletes finalized or paid records.
    """
    payslips = db.query(Payslip).filter(Payslip.id.in_(payslip_ids)).all()
    deleted_count = 0
    skipped_count = 0

    for p in payslips:
        if p.status == "draft":
            db.delete(p)
            deleted_count += 1
        else:
            skipped_count += 1

    db.commit()

    if actor and deleted_count > 0:
        audit = AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action="BULK_PAYSLIP_DELETE",
            entity="Payslip",
            old_value=None,
            new_value=f"Batch deleted {deleted_count} draft payslips. Skipped {skipped_count} finalized/paid payslips.",
        )
        db.add(audit)
        db.commit()

    return {
        "deleted_count": deleted_count,
        "skipped_locked_count": skipped_count,
    }


def bulk_generate_payslips_zip(
    db: Session,
    payslip_ids: List[int],
) -> io.BytesIO:
    """
    Generates PDF documents for each selected payslip and packages them
    into an in-memory ZIP archive with guaranteed unique filenames.
    Uses ultra-fast vector ReportLab rendering to handle batches in milliseconds.
    """
    from app.services.pdf_generator import generate_payslip_pdf_reportlab
    import os
    
    company = db.query(Company).first()
    payslips = db.query(Payslip).filter(Payslip.id.in_(payslip_ids)).all()

    zip_buffer = io.BytesIO()
    used_names = set()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for payslip in payslips:
            emp = payslip.employee
            if not emp:
                continue
            pdf_buffer = generate_payslip_pdf_reportlab(payslip, company, emp)
            base_filename = get_payslip_pdf_filename(payslip)

            filename = base_filename
            counter = 1
            while filename in used_names:
                name_part, ext = os.path.splitext(base_filename)
                filename = f"{name_part}_{payslip.id or counter}{ext}"
                counter += 1
            used_names.add(filename)

            zip_file.writestr(filename, pdf_buffer.getvalue())

    zip_buffer.seek(0)
    return zip_buffer


