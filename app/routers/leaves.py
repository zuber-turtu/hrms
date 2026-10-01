import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract, or_, and_

from app.database import get_db
from app.models.employee import Employee
from app.models.leave import LeaveType, LeaveBalance, LeaveApplication, WfhRequest
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.utils.timezone import get_ist_today, get_ist_now
from app.utils.security import get_safe_redirect, append_query_param
from app.services.email_service import send_leave_status_email, send_wfh_status_email
from app.templates_config import templates

router = APIRouter(prefix="/leaves")

allow_hr_admin = RoleChecker(["admin", "hr_admin", "manager"])
allow_admin_only = RoleChecker(["admin", "hr_admin"])


def ensure_employee_leave_balances(db: Session, employee_id: int, year: Optional[int] = None) -> List[LeaveBalance]:
    """
    Initializes annual leave balance records for all active leave types for the employee
    if they do not already exist for the specified year.
    """
    if year is None:
        year = get_ist_today().year

    leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).all()
    balances = []

    for lt in leave_types:
        bal = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == lt.id,
                LeaveBalance.year == year,
            )
            .first()
        )
        if not bal:
            bal = LeaveBalance(
                employee_id=employee_id,
                leave_type_id=lt.id,
                year=year,
                total_allocated=lt.default_days_per_year,
                used_days=0.0,
                pending_days=0.0,
            )
            db.add(bal)
            db.flush()
        balances.append(bal)

    db.commit()
    return balances


def calculate_leave_days(start_date: datetime.date, end_date: datetime.date, is_half_day: bool = False) -> float:
    """Calculates number of calendar leave days."""
    if is_half_day:
        return 0.5
    return float((end_date - start_date).days + 1)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def leaves_dashboard(
    request: Request,
    tab: str = "my_leaves",
    status_filter: Optional[str] = None,
    q: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    current_year = year or get_ist_today().year
    
    # 1. Ensure user's own balances are initialized
    my_balances = ensure_employee_leave_balances(db, current_user.id, current_year)
    
    # 2. Query user's own leave applications
    my_leaves_query = (
        db.query(LeaveApplication)
        .filter(LeaveApplication.employee_id == current_user.id)
        .order_by(LeaveApplication.created_at.desc())
    )
    my_leaves = my_leaves_query.all()

    # 3. Query user's own WFH requests
    my_wfh_query = (
        db.query(WfhRequest)
        .filter(WfhRequest.employee_id == current_user.id)
        .order_by(WfhRequest.created_at.desc())
    )
    my_wfh = my_wfh_query.all()

    # 4. Approvals and Team Management (for Admins & Managers)
    is_approver = current_user.role in ["admin", "hr_admin", "manager"]
    pending_leaves = []
    pending_wfh = []
    team_members = []
    all_leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).order_by(LeaveType.id.asc()).all()

    if is_approver:
        if current_user.role == "manager":
            # Subordinates in same department
            team_query = (
                db.query(Employee)
                .filter(
                    Employee.department_id == current_user.department_id,
                    Employee.role.notin_(["admin", "hr_admin"]),
                    Employee.is_active == True,
                )
            )
            team_members = team_query.all()
            team_emp_ids = [e.id for e in team_members]

            pending_leaves = (
                db.query(LeaveApplication)
                .filter(
                    LeaveApplication.employee_id.in_(team_emp_ids),
                    LeaveApplication.status == "pending",
                )
                .order_by(LeaveApplication.created_at.asc())
                .all()
            )
            pending_wfh = (
                db.query(WfhRequest)
                .filter(
                    WfhRequest.employee_id.in_(team_emp_ids),
                    WfhRequest.status == "pending",
                )
                .order_by(WfhRequest.created_at.asc())
                .all()
            )
        else:
            # Admins & HR Admins see all non-admin pending requests
            team_members = db.query(Employee).filter(Employee.is_active == True, Employee.role != "admin").all()
            pending_leaves = (
                db.query(LeaveApplication)
                .join(Employee, LeaveApplication.employee_id == Employee.id)
                .filter(LeaveApplication.status == "pending", Employee.role != "admin")
                .order_by(LeaveApplication.created_at.asc())
                .all()
            )
            pending_wfh = (
                db.query(WfhRequest)
                .join(Employee, WfhRequest.employee_id == Employee.id)
                .filter(WfhRequest.status == "pending", Employee.role != "admin")
                .order_by(WfhRequest.created_at.asc())
                .all()
            )

    # 5. Team WFH & Leave Calendar / Today's Off
    today = get_ist_today()
    active_today_wfh = (
        db.query(WfhRequest)
        .filter(
            WfhRequest.status == "approved",
            WfhRequest.start_date <= today,
            WfhRequest.end_date >= today,
        )
        .all()
    )
    active_today_leaves = (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.status == "approved",
            LeaveApplication.start_date <= today,
            LeaveApplication.end_date >= today,
        )
        .all()
    )

    context = {
        "user": current_user,
        "tab": tab,
        "selected_year": current_year,
        "leave_types": all_leave_types,
        "my_balances": my_balances,
        "my_leaves": my_leaves,
        "my_wfh": my_wfh,
        "is_approver": is_approver,
        "pending_leaves": pending_leaves,
        "pending_wfh": pending_wfh,
        "team_members": team_members,
        "active_today_wfh": active_today_wfh,
        "active_today_leaves": active_today_leaves,
        "today": today,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "leaves/partials/_content.html", context)

    return templates.TemplateResponse(request, "leaves/index.html", context)


@router.post("/apply")
async def apply_leave(
    request: Request,
    background_tasks: BackgroundTasks,
    leave_type_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    is_half_day: bool = Form(False),
    half_day_session: Optional[str] = Form(None),
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(
            url="/leaves?error=Invalid+date+format.+Please+select+valid+dates.",
            status_code=303,
        )

    if s_date > e_date:
        return RedirectResponse(
            url="/leaves?error=Start+date+cannot+be+later+than+end+date.",
            status_code=303,
        )

    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id, LeaveType.is_active == True).first()
    if not leave_type:
        return RedirectResponse(
            url="/leaves?error=Selected+leave+type+is+invalid+or+inactive.",
            status_code=303,
        )

    total_days = calculate_leave_days(s_date, e_date, is_half_day)
    year = s_date.year

    # Ensure balance record
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

    # Check remaining quota for paid leave types
    if leave_type.is_paid and leave_type.code not in ["LWP", "COMP_OFF"]:
        if balance and balance.remaining_days < total_days:
            err_msg = f"Insufficient {leave_type.name} balance. Available: {balance.remaining_days} day(s), Requested: {total_days} day(s)."
            return RedirectResponse(
                url=f"/leaves?error={append_query_param('', 'error', err_msg).split('error=')[1]}",
                status_code=303,
            )

    # Check overlapping pending or approved leave requests
    overlap = (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.employee_id == current_user.id,
            LeaveApplication.status.in_(["pending", "approved"]),
            LeaveApplication.start_date <= e_date,
            LeaveApplication.end_date >= s_date,
        )
        .first()
    )
    if overlap:
        return RedirectResponse(
            url="/leaves?error=You+already+have+a+leave+application+covering+these+dates.",
            status_code=303,
        )

    application = LeaveApplication(
        employee_id=current_user.id,
        leave_type_id=leave_type.id,
        start_date=s_date,
        end_date=e_date,
        total_days=total_days,
        is_half_day=is_half_day,
        half_day_session=half_day_session if is_half_day else None,
        reason=reason.strip(),
        status="pending",
    )
    db.add(application)

    if balance:
        balance.pending_days += total_days

    db.commit()

    # Optional Email Notification in Background
    date_str = str(s_date) if s_date == e_date else f"{s_date} to {e_date}"
    background_tasks.add_task(
        send_leave_status_email,
        to_email=current_user.email,
        recipient_name=current_user.name,
        leave_type_name=leave_type.name,
        start_date=str(s_date),
        end_date=str(e_date),
        total_days=total_days,
        status="applied",
        reason=reason.strip(),
    )

    return RedirectResponse(
        url=f"/leaves?success=Leave+application+for+{total_days}+day(s)+submitted+successfully.",
        status_code=303,
    )


@router.post("/{application_id}/approve")
async def approve_leave(
    application_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    app = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Leave application not found")

    if app.status != "pending":
        return RedirectResponse(
            url="/leaves?tab=approvals&error=This+application+has+already+been+processed.",
            status_code=303,
        )

    # Manager Department Scope Check
    if current_user.role == "manager":
        if (
            not current_user.department_id
            or app.employee.department_id != current_user.department_id
            or app.employee.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to approve this request.")

    app.status = "approved"
    app.reviewed_by_id = current_user.id
    app.reviewed_at = get_ist_now()

    # Update Leave Balance
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
    if balance:
        balance.pending_days = max(0.0, balance.pending_days - app.total_days)
        balance.used_days += app.total_days

    # Audit log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="LEAVE_APPROVED",
        entity="LeaveApplication",
        entity_id=app.id,
        old_value="pending",
        new_value=f"approved by {current_user.name}",
    )
    db.add(audit)
    db.commit()

    # Email notification to applicant
    background_tasks.add_task(
        send_leave_status_email,
        to_email=app.employee.email,
        recipient_name=app.employee.name,
        leave_type_name=app.leave_type.name,
        start_date=str(app.start_date),
        end_date=str(app.end_date),
        total_days=app.total_days,
        status="approved",
        reason=app.reason,
    )

    return RedirectResponse(
        url=f"/leaves?tab=approvals&success=Leave+application+for+{app.employee.name}+approved.",
        status_code=303,
    )


@router.post("/{application_id}/reject")
async def reject_leave(
    application_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    rejection_reason: str = Form("Application declined by reviewer"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    app = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Leave application not found")

    if app.status != "pending":
        return RedirectResponse(
            url="/leaves?tab=approvals&error=This+application+has+already+been+processed.",
            status_code=303,
        )

    # Manager Department Scope Check
    if current_user.role == "manager":
        if (
            not current_user.department_id
            or app.employee.department_id != current_user.department_id
            or app.employee.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to reject this request.")

    app.status = "rejected"
    app.rejection_reason = rejection_reason.strip()
    app.reviewed_by_id = current_user.id
    app.reviewed_at = get_ist_now()

    # Revert pending balance
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
    if balance:
        balance.pending_days = max(0.0, balance.pending_days - app.total_days)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="LEAVE_REJECTED",
        entity="LeaveApplication",
        entity_id=app.id,
        old_value="pending",
        new_value=f"rejected: {rejection_reason}",
    )
    db.add(audit)
    db.commit()

    # Email notification
    background_tasks.add_task(
        send_leave_status_email,
        to_email=app.employee.email,
        recipient_name=app.employee.name,
        leave_type_name=app.leave_type.name,
        start_date=str(app.start_date),
        end_date=str(app.end_date),
        total_days=app.total_days,
        status="rejected",
        reason=app.reason,
        reviewer_remarks=rejection_reason.strip(),
    )

    return RedirectResponse(
        url=f"/leaves?tab=approvals&success=Leave+application+for+{app.employee.name}+rejected.",
        status_code=303,
    )


@router.post("/{application_id}/cancel")
async def cancel_leave(
    application_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    app = db.query(LeaveApplication).filter(LeaveApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Leave application not found")

    if app.employee_id != current_user.id and current_user.role not in ["admin", "hr_admin"]:
        raise HTTPException(status_code=403, detail="Not permitted to cancel this request")

    if app.status not in ["pending", "approved"]:
        return RedirectResponse(
            url="/leaves?error=Only+pending+or+approved+leaves+can+be+cancelled.",
            status_code=303,
        )

    # Revert balances
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

    if balance:
        if app.status == "pending":
            balance.pending_days = max(0.0, balance.pending_days - app.total_days)
        elif app.status == "approved":
            balance.used_days = max(0.0, balance.used_days - app.total_days)

    app.status = "cancelled"
    db.commit()

    return RedirectResponse(
        url="/leaves?success=Leave+application+cancelled+successfully.",
        status_code=303,
    )


# =========================================================================
# WORK FROM HOME (WFH) APPLICATION & ALLOCATION
# =========================================================================

@router.post("/wfh/apply")
async def apply_wfh(
    request: Request,
    background_tasks: BackgroundTasks,
    start_date: str = Form(...),
    end_date: str = Form(...),
    is_half_day: bool = Form(False),
    half_day_session: Optional[str] = Form(None),
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(
            url="/leaves?error=Invalid+date+format.+Please+select+valid+dates.",
            status_code=303,
        )

    if s_date > e_date:
        return RedirectResponse(
            url="/leaves?error=Start+date+cannot+be+later+than+end+date.",
            status_code=303,
        )

    total_days = calculate_leave_days(s_date, e_date, is_half_day)

    # Check overlapping WFH requests
    overlap = (
        db.query(WfhRequest)
        .filter(
            WfhRequest.employee_id == current_user.id,
            WfhRequest.status.in_(["pending", "approved"]),
            WfhRequest.start_date <= e_date,
            WfhRequest.end_date >= s_date,
        )
        .first()
    )
    if overlap:
        return RedirectResponse(
            url="/leaves?error=You+already+have+a+WFH+request+covering+these+dates.",
            status_code=303,
        )

    wfh = WfhRequest(
        employee_id=current_user.id,
        start_date=s_date,
        end_date=e_date,
        total_days=total_days,
        is_half_day=is_half_day,
        half_day_session=half_day_session if is_half_day else None,
        reason=reason.strip(),
        status="pending",
        is_direct_allocation=False,
    )
    db.add(wfh)
    db.commit()

    return RedirectResponse(
        url=f"/leaves?success=WFH+request+for+{total_days}+day(s)+submitted+successfully.",
        status_code=303,
    )


@router.post("/wfh/allocate")
async def allocate_wfh(
    request: Request,
    background_tasks: BackgroundTasks,
    employee_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form("Direct WFH Allocation by Management"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Directly allocates WFH for an employee by Admin or Manager (Auto-Approved)."""
    target_emp = db.query(Employee).filter(Employee.id == employee_id, Employee.is_active == True).first()
    if not target_emp:
        return RedirectResponse(
            url="/leaves?tab=approvals&error=Selected+employee+not+found.",
            status_code=303,
        )

    if current_user.role == "manager":
        if (
            not current_user.department_id
            or target_emp.department_id != current_user.department_id
            or target_emp.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to allocate WFH for this employee.")

    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(
            url="/leaves?tab=approvals&error=Invalid+date+format.",
            status_code=303,
        )

    if s_date > e_date:
        return RedirectResponse(
            url="/leaves?tab=approvals&error=Start+date+cannot+be+after+end+date.",
            status_code=303,
        )

    total_days = calculate_leave_days(s_date, e_date, False)

    wfh = WfhRequest(
        employee_id=target_emp.id,
        start_date=s_date,
        end_date=e_date,
        total_days=total_days,
        is_half_day=False,
        reason=reason.strip(),
        status="approved",
        is_direct_allocation=True,
        reviewed_by_id=current_user.id,
        reviewed_at=get_ist_now(),
    )
    db.add(wfh)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="WFH_DIRECT_ALLOCATION",
        entity="WfhRequest",
        entity_id=target_emp.id,
        old_value=None,
        new_value=f"Allocated WFH for {target_emp.name} ({s_date} to {e_date})",
    )
    db.add(audit)
    db.commit()

    background_tasks.add_task(
        send_wfh_status_email,
        to_email=target_emp.email,
        recipient_name=target_emp.name,
        start_date=str(s_date),
        end_date=str(e_date),
        total_days=total_days,
        status="allocated",
        reason=reason.strip(),
        reviewer_remarks=f"Allocated by {current_user.name}",
    )

    return RedirectResponse(
        url=f"/leaves?tab=approvals&success=WFH+successfully+allocated+to+{target_emp.name}+for+{total_days}+day(s).",
        status_code=303,
    )


@router.post("/wfh/{request_id}/approve")
async def approve_wfh(
    request_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    wfh = db.query(WfhRequest).filter(WfhRequest.id == request_id).first()
    if not wfh:
        raise HTTPException(status_code=404, detail="WFH request not found")

    if wfh.status != "pending":
        return RedirectResponse(
            url="/leaves?tab=approvals&error=This+WFH+request+has+already+been+processed.",
            status_code=303,
        )

    if current_user.role == "manager":
        if (
            not current_user.department_id
            or wfh.employee.department_id != current_user.department_id
            or wfh.employee.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to approve this WFH request.")

    wfh.status = "approved"
    wfh.reviewed_by_id = current_user.id
    wfh.reviewed_at = get_ist_now()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="WFH_APPROVED",
        entity="WfhRequest",
        entity_id=wfh.id,
        old_value="pending",
        new_value=f"approved by {current_user.name}",
    )
    db.add(audit)
    db.commit()

    background_tasks.add_task(
        send_wfh_status_email,
        to_email=wfh.employee.email,
        recipient_name=wfh.employee.name,
        start_date=str(wfh.start_date),
        end_date=str(wfh.end_date),
        total_days=wfh.total_days,
        status="approved",
        reason=wfh.reason,
    )

    return RedirectResponse(
        url=f"/leaves?tab=approvals&success=WFH+request+for+{wfh.employee.name}+approved.",
        status_code=303,
    )


@router.post("/wfh/{request_id}/reject")
async def reject_wfh(
    request_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    rejection_reason: str = Form("Request declined by manager/HR"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    wfh = db.query(WfhRequest).filter(WfhRequest.id == request_id).first()
    if not wfh:
        raise HTTPException(status_code=404, detail="WFH request not found")

    if wfh.status != "pending":
        return RedirectResponse(
            url="/leaves?tab=approvals&error=This+WFH+request+has+already+been+processed.",
            status_code=303,
        )

    if current_user.role == "manager":
        if (
            not current_user.department_id
            or wfh.employee.department_id != current_user.department_id
            or wfh.employee.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(status_code=403, detail="Not authorized to reject this WFH request.")

    wfh.status = "rejected"
    wfh.rejection_reason = rejection_reason.strip()
    wfh.reviewed_by_id = current_user.id
    wfh.reviewed_at = get_ist_now()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="WFH_REJECTED",
        entity="WfhRequest",
        entity_id=wfh.id,
        old_value="pending",
        new_value=f"rejected: {rejection_reason}",
    )
    db.add(audit)
    db.commit()

    background_tasks.add_task(
        send_wfh_status_email,
        to_email=wfh.employee.email,
        recipient_name=wfh.employee.name,
        start_date=str(wfh.start_date),
        end_date=str(wfh.end_date),
        total_days=wfh.total_days,
        status="rejected",
        reason=wfh.reason,
        reviewer_remarks=rejection_reason.strip(),
    )

    return RedirectResponse(
        url=f"/leaves?tab=approvals&success=WFH+request+for+{wfh.employee.name}+rejected.",
        status_code=303,
    )


@router.post("/wfh/{request_id}/cancel")
async def cancel_wfh(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    wfh = db.query(WfhRequest).filter(WfhRequest.id == request_id).first()
    if not wfh:
        raise HTTPException(status_code=404, detail="WFH request not found")

    if wfh.employee_id != current_user.id and current_user.role not in ["admin", "hr_admin"]:
        raise HTTPException(status_code=403, detail="Not permitted to cancel this request")

    wfh.status = "cancelled"
    db.commit()

    return RedirectResponse(
        url="/leaves?success=WFH+request+cancelled+successfully.",
        status_code=303,
    )


# =========================================================================
# LEAVE BALANCES QUOTA MANAGEMENT (ADMIN ONLY)
# =========================================================================

@router.post("/balances/{balance_id}/adjust")
async def adjust_leave_balance(
    balance_id: int,
    request: Request,
    total_allocated: float = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    bal = db.query(LeaveBalance).filter(LeaveBalance.id == balance_id).first()
    if not bal:
        raise HTTPException(status_code=404, detail="Leave balance record not found")

    old_alloc = bal.total_allocated
    bal.total_allocated = max(0.0, total_allocated)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="LEAVE_BALANCE_ADJUSTED",
        entity="LeaveBalance",
        entity_id=bal.id,
        old_value=str(old_alloc),
        new_value=str(bal.total_allocated),
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/leaves?tab=team_balances&success=Quota+updated+for+{bal.employee.name}+({bal.leave_type.name}).",
        status_code=303,
    )
