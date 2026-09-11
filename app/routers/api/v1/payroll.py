from typing import List, Optional
import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.payroll import Payslip
from app.models.company import Company
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.services.payroll_calculator import generate_draft_payslip
from app.services.pdf_generator import generate_payslip_pdf
from app.schemas.payroll import (
    GenerateDraftRequest,
    GenerateBulkDraftRequest,
    PayslipOut,
    PayslipUpdate,
    PayrollSummary,
)

router = APIRouter(prefix="/payroll", tags=["Payroll"])
allow_hr_admin = RoleChecker(["admin", "hr_admin"])


def _format_payslip_out(payslip: Payslip) -> PayslipOut:
    return PayslipOut(
        id=payslip.id,
        employee_id=payslip.employee_id,
        month=payslip.month,
        year=payslip.year,
        generated_on=payslip.generated_on,
        payable_days=payslip.payable_days or 22,
        days_worked=payslip.days_worked or 0.0,
        basic=payslip.basic or 0.0,
        hra=payslip.hra or 0.0,
        allowances=payslip.allowances or 0.0,
        bonus=payslip.bonus or 0.0,
        pf=payslip.pf or 0.0,
        tax=payslip.tax or 0.0,
        other_deductions=payslip.other_deductions or 0.0,
        net_salary=payslip.net_salary or 0.0,
        status=payslip.status or "draft",
        employee_name=payslip.employee.name if payslip.employee else None,
        employee_email=payslip.employee.email if payslip.employee else None,
        department_name=payslip.employee.department.name if payslip.employee and payslip.employee.department else None,
        designation_title=payslip.employee.designation.title if payslip.employee and payslip.employee.designation else None,
    )


@router.get("", response_model=List[PayslipOut])
@router.get("/", response_model=List[PayslipOut])
async def list_payslips(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    employee_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    query = db.query(Payslip)

    # Role-based scoping: normal employees can only see their own payslips
    if current_user.role not in ["admin", "hr_admin"]:
        query = query.filter(Payslip.employee_id == current_user.id)
    elif employee_id is not None:
        query = query.filter(Payslip.employee_id == employee_id)

    if month is not None:
        query = query.filter(Payslip.month == month)
    if year is not None:
        query = query.filter(Payslip.year == year)
    if status_filter:
        query = query.filter(Payslip.status == status_filter)

    records = query.order_by(Payslip.year.desc(), Payslip.month.desc()).all()
    return [_format_payslip_out(p) for p in records]


@router.get("/summary", response_model=PayrollSummary)
async def get_payroll_summary(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    query = db.query(Payslip)
    if month is not None:
        query = query.filter(Payslip.month == month)
    if year is not None:
        query = query.filter(Payslip.year == year)

    records = query.order_by(Payslip.year.desc(), Payslip.month.desc()).all()
    total_net = sum(p.net_salary or 0.0 for p in records)
    draft_count = sum(1 for p in records if p.status == "draft")
    finalized_count = sum(1 for p in records if p.status in ["finalized", "paid"])

    return PayrollSummary(
        month=month,
        year=year,
        total_records=len(records),
        total_net=round(total_net, 2),
        draft_count=draft_count,
        finalized_count=finalized_count,
        payslips=[_format_payslip_out(p) for p in records],
    )


@router.post("/generate-draft", response_model=PayslipOut, status_code=status.HTTP_201_CREATED)
async def create_draft_payslip(
    req: GenerateDraftRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    # Verify employee exists
    employee = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {req.employee_id} not found"
        )

    # Check if payslip already exists for this month/year
    existing = db.query(Payslip).filter(
        Payslip.employee_id == req.employee_id,
        Payslip.month == req.month,
        Payslip.year == req.year,
    ).first()

    if existing:
        return _format_payslip_out(existing)

    draft_data = generate_draft_payslip(db, req.employee_id, req.month, req.year)
    if not draft_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to compute draft payslip data"
        )

    payslip = Payslip(**draft_data)
    db.add(payslip)
    db.commit()
    db.refresh(payslip)

    # Audit log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="PAYSLIP_DRAFT_GENERATE",
        entity="Payslip",
        entity_id=payslip.id,
        old_value=None,
        new_value=f"Draft generated for employee {employee.name} ({req.month}/{req.year})",
    )
    db.add(audit)
    db.commit()

    return _format_payslip_out(payslip)


@router.post("/generate-bulk-draft", response_model=List[PayslipOut])
async def create_bulk_draft_payslips(
    req: GenerateBulkDraftRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    employees = db.query(Employee).all()
    created_or_found = []

    for emp in employees:
        existing = db.query(Payslip).filter(
            Payslip.employee_id == emp.id,
            Payslip.month == req.month,
            Payslip.year == req.year,
        ).first()

        if existing:
            created_or_found.append(_format_payslip_out(existing))
            continue

        draft_data = generate_draft_payslip(db, emp.id, req.month, req.year)
        if draft_data:
            payslip = Payslip(**draft_data)
            db.add(payslip)
            db.commit()
            db.refresh(payslip)
            created_or_found.append(_format_payslip_out(payslip))

    return created_or_found


@router.get("/payslips/{payslip_id}", response_model=PayslipOut)
async def get_payslip(
    payslip_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payslip with ID {payslip_id} not found"
        )

    if current_user.role not in ["admin", "hr_admin"] and payslip.employee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to access this payslip"
        )

    return _format_payslip_out(payslip)


@router.put("/payslips/{payslip_id}", response_model=PayslipOut)
async def update_payslip(
    payslip_id: int,
    payload: PayslipUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payslip with ID {payslip_id} not found"
        )

    old_val = (
        f"Date: {payslip.generated_on}, Basic: {payslip.basic}, Days: {payslip.days_worked}/{payslip.payable_days}, "
        f"Net: {payslip.net_salary}, Status: {payslip.status}"
    )

    if payload.generated_on is not None:
        payslip.generated_on = payload.generated_on
    if payload.payable_days is not None:
        payslip.payable_days = payload.payable_days
    if payload.days_worked is not None:
        payslip.days_worked = payload.days_worked
    if payload.basic is not None:
        payslip.basic = payload.basic
    if payload.hra is not None:
        payslip.hra = payload.hra
    if payload.allowances is not None:
        payslip.allowances = payload.allowances
    if payload.bonus is not None:
        payslip.bonus = payload.bonus
    if payload.pf is not None:
        payslip.pf = payload.pf
    if payload.tax is not None:
        payslip.tax = payload.tax
    if payload.other_deductions is not None:
        payslip.other_deductions = payload.other_deductions
    if payload.status is not None:
        payslip.status = payload.status

    if payload.net_salary is not None:
        payslip.net_salary = payload.net_salary
    else:
        payslip.net_salary = (
            (payslip.basic or 0.0) + (payslip.hra or 0.0) + (payslip.allowances or 0.0) + (payslip.bonus or 0.0)
        ) - ((payslip.pf or 0.0) + (payslip.tax or 0.0) + (payslip.other_deductions or 0.0))

    new_val = (
        f"Date: {payslip.generated_on}, Basic: {payslip.basic}, Days: {payslip.days_worked}/{payslip.payable_days}, "
        f"Net: {payslip.net_salary}, Status: {payslip.status}"
    )

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
    db.refresh(payslip)

    return _format_payslip_out(payslip)


@router.get("/payslips/{payslip_id}/pdf")
async def download_payslip_pdf(
    payslip_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    payslip = db.query(Payslip).filter(Payslip.id == payslip_id).first()
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payslip with ID {payslip_id} not found"
        )

    if current_user.role not in ["admin", "hr_admin"] and payslip.employee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to download this payslip"
        )

    company = db.query(Company).first()
    pdf_buffer = generate_payslip_pdf(payslip, company, payslip.employee)

    headers = {
        "Content-Disposition": f'attachment; filename="payslip_{payslip.month}_{payslip.year}.pdf"'
    }
    return Response(
        content=pdf_buffer.read(),
        media_type="application/pdf",
        headers=headers,
    )
