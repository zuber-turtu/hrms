from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import datetime

from app.database import get_db
from app.models.employee import Employee
from app.models.leave import LeaveType, LeaveBalance, LeaveApplication, WfhRequest
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.utils.timezone import get_ist_today, get_ist_now
from app.routers.leaves import ensure_employee_leave_balances, calculate_leave_days, is_leave_type_applicable, auto_lapse_pending_requests
from app.schemas.leave import (
    LeaveTypeOut,
    LeaveBalanceOut,
    LeaveApplicationCreate,
    LeaveApplicationOut,
    LeaveReviewRequest,
    WfhRequestCreate,
    WfhDirectAllocateRequest,
    WfhRequestOut,
)

router = APIRouter(prefix="/leaves", tags=["Leaves & WFH"])
allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin", "manager"])


@router.get("/types", response_model=List[LeaveTypeOut])
async def api_get_leave_types(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """List all active leave categories/types applicable for current user profile."""
    all_types = db.query(LeaveType).filter(LeaveType.is_active == True).order_by(LeaveType.id.asc()).all()
    return [lt for lt in all_types if is_leave_type_applicable(lt, current_user.gender)]


@router.get("/balances", response_model=List[LeaveBalanceOut])
async def api_get_my_leave_balances(
    year: Optional[int] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Retrieve annual leave quotas, used, pending, and remaining balances."""
    target_emp_id = current_user.id
    if employee_id and employee_id != current_user.id:
        if current_user.role not in ["super_admin", "admin", "hr", "hr_admin", "manager"]:
            raise HTTPException(status_code=403, detail="Not authorized to view other employee balances")
        target_emp_id = employee_id

    target_year = year or get_ist_today().year
    auto_lapse_pending_requests(db)
    raw_balances = ensure_employee_leave_balances(db, target_emp_id, target_year)

    results = []
    for b in raw_balances:
        results.append(
            LeaveBalanceOut(
                id=b.id,
                employee_id=b.employee_id,
                leave_type_id=b.leave_type_id,
                leave_type_name=b.leave_type.name if b.leave_type else "Leave",
                leave_type_code=b.leave_type.code if b.leave_type else "LV",
                color_code=b.leave_type.color_code if b.leave_type else "#008080",
                is_paid=b.leave_type.is_paid if b.leave_type else True,
                year=b.year,
                total_allocated=b.total_allocated,
                used_days=b.used_days,
                pending_days=b.pending_days,
                remaining_days=b.remaining_days,
            )
        )
    return results


@router.post("/apply", response_model=LeaveApplicationOut)
async def api_apply_leave(
    payload: LeaveApplicationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Submit a new leave application."""
    auto_lapse_pending_requests(db)
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")

    leave_type = db.query(LeaveType).filter(LeaveType.id == payload.leave_type_id, LeaveType.is_active == True).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Invalid leave type")

    # Gender-specific eligibility check
    if not is_leave_type_applicable(leave_type.code, current_user.gender):
        if leave_type.code == "ML":
            raise HTTPException(status_code=400, detail="Maternity leave is applicable for female employees only")
        elif leave_type.code == "PL_PAT":
            raise HTTPException(status_code=400, detail="Paternity leave is applicable for male employees only")
        else:
            raise HTTPException(status_code=400, detail=f"{leave_type.name} is not applicable for your profile")

    total_days = calculate_leave_days(payload.start_date, payload.end_date, payload.is_half_day)
    year = payload.start_date.year

    ensure_employee_leave_balances(db, current_user.id, year)
    balance = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == current_user.id,
            LeaveBalance.leave_type_id == leave_type.id,
            LeaveBalance.year == year,
        )
        .first()
    )

    # Strict Quota Enforcement
    is_lwp_unlimited = (leave_type.code == "LWP" and not leave_type.is_paid and leave_type.default_days_per_year == 0.0 and (balance.total_allocated if balance else 0.0) == 0.0)
    
    if not is_lwp_unlimited:
        avail_days = balance.remaining_days if balance else 0.0
        if avail_days < total_days:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient leave balance for {leave_type.name}. You have {avail_days:g} day(s) remaining in your quota, but requested {total_days:g} day(s).",
            )

    overlap = (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.employee_id == current_user.id,
            LeaveApplication.status.in_(["pending", "approved"]),
            LeaveApplication.start_date <= payload.end_date,
            LeaveApplication.end_date >= payload.start_date,
        )
        .first()
    )
    if overlap:
        raise HTTPException(status_code=400, detail="An overlapping leave application already exists")

    application = LeaveApplication(
        employee_id=current_user.id,
        leave_type_id=leave_type.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        total_days=total_days,
        is_half_day=payload.is_half_day,
        half_day_session=payload.half_day_session if payload.is_half_day else None,
        reason=payload.reason.strip(),
        status="pending",
    )
    db.add(application)

    if balance:
        balance.pending_days += total_days

    db.commit()
    db.refresh(application)

    background_tasks.add_task(
        send_leave_status_email,
        to_email=current_user.email,
        recipient_name=current_user.name,
        leave_type_name=leave_type.name,
        start_date=str(payload.start_date),
        end_date=str(payload.end_date),
        total_days=total_days,
        status="applied",
        reason=payload.reason.strip(),
    )

    return LeaveApplicationOut(
        id=application.id,
        employee_id=application.employee_id,
        employee_name=current_user.name,
        leave_type_id=application.leave_type_id,
        leave_type_name=leave_type.name,
        leave_type_code=leave_type.code,
        start_date=application.start_date,
        end_date=application.end_date,
        total_days=application.total_days,
        is_half_day=application.is_half_day,
        half_day_session=application.half_day_session,
        reason=application.reason,
        status=application.status,
        reviewed_by_id=None,
        reviewed_by_name=None,
        reviewed_at=None,
        rejection_reason=None,
        created_at=application.created_at,
    )


@router.get("/applications", response_model=List[LeaveApplicationOut])
async def api_get_leave_applications(
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Get leave applications. Employees see their own; Admins/Managers see team applications."""
    auto_lapse_pending_requests(db)
    query = db.query(LeaveApplication)

    if current_user.role in ["employee", "intern"]:
        query = query.filter(LeaveApplication.employee_id == current_user.id)
    elif current_user.role == "manager":
        query = query.join(Employee, LeaveApplication.employee_id == Employee.id).filter(
            Employee.department_id == current_user.department_id,
            Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"]),
        )
        if employee_id:
            query = query.filter(LeaveApplication.employee_id == employee_id)
    else:
        if employee_id:
            query = query.filter(LeaveApplication.employee_id == employee_id)

    if status_filter and status_filter.strip() != "all":
        query = query.filter(LeaveApplication.status == status_filter.strip())

    apps = query.order_by(LeaveApplication.created_at.desc()).all()
    results = []
    for a in apps:
        results.append(
            LeaveApplicationOut(
                id=a.id,
                employee_id=a.employee_id,
                employee_name=a.employee.name if a.employee else None,
                leave_type_id=a.leave_type_id,
                leave_type_name=a.leave_type.name if a.leave_type else None,
                leave_type_code=a.leave_type.code if a.leave_type else None,
                start_date=a.start_date,
                end_date=a.end_date,
                total_days=a.total_days,
                is_half_day=a.is_half_day,
                half_day_session=a.half_day_session,
                reason=a.reason,
                status=a.status,
                reviewed_by_id=a.reviewed_by_id,
                reviewed_by_name=a.reviewed_by.name if a.reviewed_by else None,
                reviewed_at=a.reviewed_at,
                rejection_reason=a.rejection_reason,
                created_at=a.created_at,
            )
        )
    return results


@router.post("/applications/{application_id}/review")
async def api_review_leave(
    application_id: int,
    payload: LeaveReviewRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Approve or Reject a pending leave application (Managers and Admins)."""
    app = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Leave application not found")

    today = get_ist_today()
    if app.status != "pending" or app.start_date < today:
        if app.status == "pending" and app.start_date < today:
            auto_lapse_pending_requests(db)
        raise HTTPException(status_code=400, detail="This application has already been processed or has lapsed")

    if current_user.role == "manager":
        if (
            not current_user.department_id
            or app.employee.department_id != current_user.department_id
            or app.employee.role in ["super_admin", "admin", "hr", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to review this application")

    year = app.start_date.year
    balance = (
        db.query(LeaveBalance)
        .filter(
            LeaveBalance.employee_id == app.employee_id,
            LeaveBalance.leave_type_id == app.leave_type_id,
            LeaveBalance.year == year,
        )
        .first()
    )

    if payload.status == "approved":
        app.status = "approved"
        app.reviewed_by_id = current_user.id
        app.reviewed_at = get_ist_now()
        if balance:
            balance.pending_days = max(0.0, balance.pending_days - app.total_days)
            balance.used_days += app.total_days
    elif payload.status == "rejected":
        app.status = "rejected"
        app.rejection_reason = payload.rejection_reason
        app.reviewed_by_id = current_user.id
        app.reviewed_at = get_ist_now()
        if balance:
            balance.pending_days = max(0.0, balance.pending_days - app.total_days)
    else:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    db.commit()

    background_tasks.add_task(
        send_leave_status_email,
        to_email=app.employee.email,
        recipient_name=app.employee.name,
        leave_type_name=app.leave_type.name,
        start_date=str(app.start_date),
        end_date=str(app.end_date),
        total_days=app.total_days,
        status=app.status,
        reason=app.reason,
        reviewer_remarks=app.rejection_reason,
    )

    return {"message": f"Leave application {payload.status} successfully.", "application_id": app.id}


# =========================================================================
# WFH REST ENDPOINTS
# =========================================================================

@router.post("/wfh/apply", response_model=WfhRequestOut)
async def api_apply_wfh(
    payload: WfhRequestCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Apply for Work From Home (WFH)."""
    auto_lapse_pending_requests(db)
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")

    total_days = calculate_leave_days(payload.start_date, payload.end_date, payload.is_half_day)

    wfh = WfhRequest(
        employee_id=current_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        total_days=total_days,
        is_half_day=payload.is_half_day,
        half_day_session=payload.half_day_session if payload.is_half_day else None,
        reason=payload.reason.strip(),
        status="pending",
        is_direct_allocation=False,
    )
    db.add(wfh)
    db.commit()
    db.refresh(wfh)

    return WfhRequestOut(
        id=wfh.id,
        employee_id=wfh.employee_id,
        employee_name=current_user.name,
        start_date=wfh.start_date,
        end_date=wfh.end_date,
        total_days=wfh.total_days,
        is_half_day=wfh.is_half_day,
        half_day_session=wfh.half_day_session,
        reason=wfh.reason,
        status=wfh.status,
        is_direct_allocation=wfh.is_direct_allocation,
        reviewed_by_id=None,
        reviewed_by_name=None,
        reviewed_at=None,
        rejection_reason=None,
        created_at=wfh.created_at,
    )


@router.post("/wfh/allocate", response_model=WfhRequestOut)
async def api_allocate_wfh(
    payload: WfhDirectAllocateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Directly allocate WFH to an employee without requiring prior application (Managers & Admins)."""
    target_emp = db.query(Employee).filter(Employee.id == payload.employee_id, Employee.is_active == True).first()
    if not target_emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if current_user.role == "manager":
        if (
            not current_user.department_id
            or target_emp.department_id != current_user.department_id
            or target_emp.role in ["super_admin", "admin", "hr", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to allocate WFH for this employee")

    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")

    total_days = calculate_leave_days(payload.start_date, payload.end_date, False)

    wfh = WfhRequest(
        employee_id=target_emp.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        total_days=total_days,
        is_half_day=False,
        reason=payload.reason.strip(),
        status="approved",
        is_direct_allocation=True,
        reviewed_by_id=current_user.id,
        reviewed_at=get_ist_now(),
    )
    db.add(wfh)
    db.commit()
    db.refresh(wfh)

    background_tasks.add_task(
        send_wfh_status_email,
        to_email=target_emp.email,
        recipient_name=target_emp.name,
        start_date=str(payload.start_date),
        end_date=str(payload.end_date),
        total_days=total_days,
        status="allocated",
        reason=payload.reason.strip(),
        reviewer_remarks=f"Directly allocated by {current_user.name}",
    )

    return WfhRequestOut(
        id=wfh.id,
        employee_id=wfh.employee_id,
        employee_name=target_emp.name,
        start_date=wfh.start_date,
        end_date=wfh.end_date,
        total_days=wfh.total_days,
        is_half_day=wfh.is_half_day,
        half_day_session=wfh.half_day_session,
        reason=wfh.reason,
        status=wfh.status,
        is_direct_allocation=wfh.is_direct_allocation,
        reviewed_by_id=current_user.id,
        reviewed_by_name=current_user.name,
        reviewed_at=wfh.reviewed_at,
        rejection_reason=None,
        created_at=wfh.created_at,
    )
