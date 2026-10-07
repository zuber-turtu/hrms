import datetime
import re
from typing import Optional, List, Union
from fastapi import APIRouter, Depends, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract, or_, and_

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department
from app.models.leave import LeaveType, LeaveBalance, LeaveApplication, WfhRequest
from app.models.company import Company
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.utils.timezone import get_ist_today, get_ist_now
from app.utils.security import get_safe_redirect, append_query_param
from app.services.email_service import send_leave_status_email, send_wfh_status_email
from app.templates_config import templates
from app.utils.flash import flash_redirect
from app.services.excel_exporter import export_leaves_excel, export_leave_balances_excel

router = APIRouter(prefix="/leaves")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin", "manager"])
allow_admin_only = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])
allow_super_admin_only = RoleChecker(["super_admin"])



def is_leave_type_applicable(leave_item: Union[LeaveType, str], gender: Optional[str]) -> bool:
    """
    Checks if a leave type is applicable based on employee gender.
    Supports either LeaveType object or leave_code string.
    - If leave_type.applicable_gender == 'female', only applicable for female employees ('female', 'f', 'woman').
    - If leave_type.applicable_gender == 'male', only applicable for male employees (non-female).
    - If leave_type.applicable_gender == 'all', applicable for all workforce members.
    - Fallback legacy code rules for 'ML' (female) and 'PL_PAT' (male).
    """
    g = (gender or "").strip().lower()
    is_female = g in ["female", "f", "woman"]

    if isinstance(leave_item, LeaveType):
        rule = (getattr(leave_item, "applicable_gender", None) or "all").strip().lower()
        if rule == "female":
            return is_female
        elif rule == "male":
            return not is_female
        elif rule == "all":
            return True
        code = leave_item.code
    else:
        code = str(leave_item)

    if code == "ML":
        return is_female
    if code == "PL_PAT":
        return not is_female
    return True


def can_user_approve_request(current_user: Employee, target_employee: Employee) -> bool:
    """
    Strict 6-Tier Hierarchy Enforcement:
    Tier 1: Super Admin (Supreme Authority)
    Tier 2: Admin
    Tier 3: HR / HR Admin
    Tier 4: Manager
    Tier 5: Employee
    Tier 6: Intern
    """
    if not current_user or not target_employee:
        return False
    if current_user.id == target_employee.id:
        return False  # Zero circular self-approvals

    c_role = current_user.role
    t_role = target_employee.role

    # Super Admin has supreme master approval authority over all accounts
    if c_role == "super_admin" or getattr(current_user, "is_super_admin", False):
        return True

    # Super Admin requests can never be approved by anyone else
    if t_role == "super_admin":
        return False

    # Admin can approve HR, Managers, Employees, Interns (cannot approve other Admins)
    if c_role == "admin":
        return t_role in ["hr", "hr_admin", "manager", "employee", "intern"]

    # HR can approve Managers, Employees, Interns (cannot approve Admins or peer HRs)
    if c_role in ["hr", "hr_admin"]:
        return t_role in ["manager", "employee", "intern"]

    # Manager can approve departmental Employees and Interns
    if c_role == "manager":
        if t_role in ["employee", "intern"]:
            return bool(current_user.department_id and current_user.department_id == target_employee.department_id)
        return False

    return False


def auto_lapse_pending_requests(db: Session) -> dict:
    """
    Automatically transitions all pending Leave Applications and WFH Requests whose
    scheduled start date has passed (start_date < today in IST) to 'lapsed' status.
    Releases locked pending leave balance quotas so employees regain their quota.
    """
    today = get_ist_today()
    now_ist = get_ist_now()

    # 1. Pending Leave Applications with start_date < today
    past_pending_leaves = (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.status == "pending",
            LeaveApplication.start_date < today,
        )
        .all()
    )

    lapsed_leave_count = 0
    for app in past_pending_leaves:
        app.status = "lapsed"
        app.rejection_reason = "System: Scheduled start date has passed without approval (Lapsed)"
        app.reviewed_at = now_ist
        lapsed_leave_count += 1

        # Revert pending balance directly if balance row exists
        balance = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.employee_id == app.employee_id,
                LeaveBalance.leave_type_id == app.leave_type_id,
                LeaveBalance.year == app.start_date.year,
            )
            .first()
        )
        if balance:
            balance.pending_days = max(0.0, balance.pending_days - app.total_days)

    # 2. Pending WFH Requests with start_date < today
    past_pending_wfh = (
        db.query(WfhRequest)
        .filter(
            WfhRequest.status == "pending",
            WfhRequest.start_date < today,
        )
        .all()
    )

    lapsed_wfh_count = 0
    for w in past_pending_wfh:
        w.status = "lapsed"
        w.rejection_reason = "System: Scheduled start date has passed without approval (Lapsed)"
        w.reviewed_at = now_ist
        lapsed_wfh_count += 1

    if lapsed_leave_count > 0 or lapsed_wfh_count > 0:
        db.commit()

    return {
        "lapsed_leaves": lapsed_leave_count,
        "lapsed_wfh": lapsed_wfh_count,
    }


def ensure_employee_leave_balances(
    db: Session,
    employee_id: int,
    year: Optional[int] = None,
    sync_policy_defaults: bool = False,
) -> List[LeaveBalance]:
    """
    Initializes and synchronizes annual leave balance records for all active applicable leave types
    for the employee. Recalculates used_days (approved) and pending_days (awaiting review) directly
    from actual LeaveApplication records for the specified year to guarantee 100% accurate mapping.
    Cleans up stale gender-ineligible or inactive balance rows that have 0 usage.
    """
    if year is None:
        year = get_ist_today().year

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return []

    emp_gender = employee.gender

    active_leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).order_by(LeaveType.id.asc()).all()
    
    # Query all existing balances for this employee and year
    existing_balances = db.query(LeaveBalance).filter(
        LeaveBalance.employee_id == employee_id,
        LeaveBalance.year == year,
    ).all()
    bal_by_type_id = {b.leave_type_id: b for b in existing_balances}

    # 1. Clean up stale/inapplicable balances if unused
    for b in existing_balances:
        lt = db.query(LeaveType).filter(LeaveType.id == b.leave_type_id).first()
        is_applicable = lt and lt.is_active and is_leave_type_applicable(lt, emp_gender)
        if not is_applicable:
            if (b.used_days or 0.0) == 0.0 and (b.pending_days or 0.0) == 0.0:
                db.delete(b)
                if b.leave_type_id in bal_by_type_id:
                    del bal_by_type_id[b.leave_type_id]

    balances = []

    # 2. Synchronize active and applicable leave types
    for lt in active_leave_types:
        if not is_leave_type_applicable(lt, emp_gender):
            continue

        bal = bal_by_type_id.get(lt.id)
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
        else:
            # Map quota to policy default if syncing requested OR if quota was 0.0 when policy has days > 0
            if sync_policy_defaults or (bal.total_allocated == 0.0 and lt.default_days_per_year > 0.0 and (bal.used_days or 0.0) == 0.0):
                bal.total_allocated = lt.default_days_per_year

        # Recalculate accurately from actual LeaveApplication records for this employee & year
        approved_apps = (
            db.query(LeaveApplication)
            .filter(
                LeaveApplication.employee_id == employee_id,
                LeaveApplication.leave_type_id == lt.id,
                LeaveApplication.status == "approved",
                extract("year", LeaveApplication.start_date) == year,
            )
            .all()
        )
        bal.used_days = sum(a.total_days for a in approved_apps)

        pending_apps = (
            db.query(LeaveApplication)
            .filter(
                LeaveApplication.employee_id == employee_id,
                LeaveApplication.leave_type_id == lt.id,
                LeaveApplication.status == "pending",
                extract("year", LeaveApplication.start_date) == year,
            )
            .all()
        )
        bal.pending_days = sum(a.total_days for a in pending_apps)

        balances.append(bal)

    db.commit()
    return balances


def sync_all_leave_quotas_with_policies(
    db: Session,
    year: Optional[int] = None,
    leave_type_id: Optional[int] = None,
) -> dict:
    """
    Synchronizes leave quotas across all active employees to strictly match active Leave Type policies.
    - If leave_type_id is provided, synchronizes only that specific policy.
    - If leave_type_id is None, synchronizes all active leave policies.
    - Cleans up stale gender-ineligible balance rows where used_days == 0.
    """
    if year is None:
        year = get_ist_today().year

    employees = db.query(Employee).filter(Employee.is_active == True, Employee.role != "admin").all()
    
    if leave_type_id:
        target_types = db.query(LeaveType).filter(LeaveType.id == leave_type_id).all()
    else:
        target_types = db.query(LeaveType).filter(LeaveType.is_active == True).all()

    updated_count = 0
    cleaned_count = 0

    for emp in employees:
        emp_gender = emp.gender
        for lt in target_types:
            bal = (
                db.query(LeaveBalance)
                .filter(
                    LeaveBalance.employee_id == emp.id,
                    LeaveBalance.leave_type_id == lt.id,
                    LeaveBalance.year == year,
                )
                .first()
            )
            
            if not lt.is_active or not is_leave_type_applicable(lt, emp_gender):
                if bal and (bal.used_days or 0.0) == 0.0 and (bal.pending_days or 0.0) == 0.0:
                    db.delete(bal)
                    cleaned_count += 1
                continue

            if not bal:
                bal = LeaveBalance(
                    employee_id=emp.id,
                    leave_type_id=lt.id,
                    year=year,
                    total_allocated=lt.default_days_per_year,
                    used_days=0.0,
                    pending_days=0.0,
                )
                db.add(bal)
                updated_count += 1
            else:
                bal.total_allocated = lt.default_days_per_year
                updated_count += 1

            # Recalculate ledger applications
            approved_apps = (
                db.query(LeaveApplication)
                .filter(
                    LeaveApplication.employee_id == emp.id,
                    LeaveApplication.leave_type_id == lt.id,
                    LeaveApplication.status == "approved",
                    extract("year", LeaveApplication.start_date) == year,
                )
                .all()
            )
            bal.used_days = sum(a.total_days for a in approved_apps)

            pending_apps = (
                db.query(LeaveApplication)
                .filter(
                    LeaveApplication.employee_id == emp.id,
                    LeaveApplication.leave_type_id == lt.id,
                    LeaveApplication.status == "pending",
                    extract("year", LeaveApplication.start_date) == year,
                )
                .all()
            )
            bal.pending_days = sum(a.total_days for a in pending_apps)

    db.commit()
    return {
        "employees_count": len(employees),
        "updated_count": updated_count,
        "cleaned_count": cleaned_count,
    }


def calculate_leave_days(start_date: datetime.date, end_date: datetime.date, is_half_day: bool = False) -> float:
    """Calculates number of calendar leave days."""
    if is_half_day:
        return 0.5
    return float((end_date - start_date).days + 1)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def leaves_dashboard(
    request: Request,
    tab: Optional[str] = None,
    status_filter: Optional[str] = None,
    q: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    current_year = year or get_ist_today().year
    if not tab:
        tab = "approvals" if current_user.role == "super_admin" else "my_leaves"
    
    # 0. Auto-lapse any pending leave/wfh requests whose start_date < today
    auto_lapse_pending_requests(db)

    # 1. Ensure user's own balances are initialized (gender filtered)
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

    # 4. Approvals and Team Management (for Super Admin, Admins, HRs, & Managers)
    is_approver = current_user.role in ["super_admin", "admin", "hr", "hr_admin", "manager"]
    pending_leaves = []
    pending_wfh = []
    team_members = []
    
    # Applicable leave types for current user dropdown
    all_leave_types = db.query(LeaveType).filter(LeaveType.is_active == True).order_by(LeaveType.id.asc()).all()
    applicable_leave_types = [
        lt for lt in all_leave_types
        if is_leave_type_applicable(lt, current_user.gender)
    ]
    all_departments = db.query(Department).order_by(Department.name.asc()).all()

    if is_approver:
        if current_user.role == "super_admin":
            # Super Admin sees all pending requests from all non-super-admin employees
            team_members = db.query(Employee).filter(Employee.is_active == True, Employee.role != "super_admin").all()
            pending_leaves = (
                db.query(LeaveApplication)
                .join(Employee, LeaveApplication.employee_id == Employee.id)
                .filter(LeaveApplication.status == "pending", Employee.role != "super_admin")
                .order_by(LeaveApplication.created_at.asc())
                .all()
            )
            pending_wfh = (
                db.query(WfhRequest)
                .join(Employee, WfhRequest.employee_id == Employee.id)
                .filter(WfhRequest.status == "pending", Employee.role != "super_admin")
                .order_by(WfhRequest.created_at.asc())
                .all()
            )
        elif current_user.role == "admin":
            # Admins see all pending requests from HR, Managers, Employees, Interns
            team_members = db.query(Employee).filter(
                Employee.is_active == True,
                Employee.role.notin_(["super_admin", "admin"])
            ).all()
            pending_leaves = (
                db.query(LeaveApplication)
                .join(Employee, LeaveApplication.employee_id == Employee.id)
                .filter(
                    LeaveApplication.status == "pending",
                    Employee.role.notin_(["super_admin", "admin"])
                )
                .order_by(LeaveApplication.created_at.asc())
                .all()
            )
            pending_wfh = (
                db.query(WfhRequest)
                .join(Employee, WfhRequest.employee_id == Employee.id)
                .filter(
                    WfhRequest.status == "pending",
                    Employee.role.notin_(["super_admin", "admin"])
                )
                .order_by(WfhRequest.created_at.asc())
                .all()
            )
        elif current_user.role in ["hr", "hr_admin"]:
            # HR sees all pending requests from Managers, Employees, Interns
            team_members = db.query(Employee).filter(
                Employee.is_active == True,
                Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
            ).all()
            pending_leaves = (
                db.query(LeaveApplication)
                .join(Employee, LeaveApplication.employee_id == Employee.id)
                .filter(
                    LeaveApplication.status == "pending",
                    Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
                )
                .order_by(LeaveApplication.created_at.asc())
                .all()
            )
            pending_wfh = (
                db.query(WfhRequest)
                .join(Employee, WfhRequest.employee_id == Employee.id)
                .filter(
                    WfhRequest.status == "pending",
                    Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
                )
                .order_by(WfhRequest.created_at.asc())
                .all()
            )
        elif current_user.role == "manager":
            # Subordinates in same department
            team_query = (
                db.query(Employee)
                .filter(
                    Employee.department_id == current_user.department_id,
                    Employee.role.in_(["employee", "intern"]),
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

    # 5. Team WFH & Leave Calendar / Today's Off (Approvers/Management Only)
    today = get_ist_today()
    active_today_wfh = []
    active_today_leaves = []
    if is_approver:
        if current_user.role == "manager":
            active_today_wfh = (
                db.query(WfhRequest)
                .filter(
                    WfhRequest.employee_id.in_(team_emp_ids),
                    WfhRequest.status == "approved",
                    WfhRequest.start_date <= today,
                    WfhRequest.end_date >= today,
                )
                .all()
            )
            active_today_leaves = (
                db.query(LeaveApplication)
                .filter(
                    LeaveApplication.employee_id.in_(team_emp_ids),
                    LeaveApplication.status == "approved",
                    LeaveApplication.start_date <= today,
                    LeaveApplication.end_date >= today,
                )
                .all()
            )
        else:
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

    # 6. Team Member Leave Profiles & Balances for Approvers
    team_leave_profiles = []
    if is_approver:
        for member in team_members:
            m_bals = ensure_employee_leave_balances(db, member.id, current_year)
            team_leave_profiles.append({
                "employee": member,
                "balances": m_bals,
                "total_allocated": sum(b.total_allocated for b in m_bals),
                "total_used": sum(b.used_days for b in m_bals),
                "total_pending": sum(b.pending_days for b in m_bals),
                "total_remaining": sum(b.remaining_days for b in m_bals),
            })

    context = {
        "user": current_user,
        "tab": tab,
        "selected_year": current_year,
        "leave_types": applicable_leave_types,
        "all_leave_types": all_leave_types,
        "all_departments": all_departments,
        "my_balances": my_balances,
        "my_leaves": my_leaves,
        "my_wfh": my_wfh,
        "is_approver": is_approver,
        "pending_leaves": pending_leaves,
        "pending_wfh": pending_wfh,
        "team_members": team_members,
        "team_leave_profiles": team_leave_profiles,
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
    if current_user.role == "super_admin":
        return flash_redirect(
            url="/leaves",
            message="Super Admin accounts are exempt from submitting personal leave applications.",
            category="error",
        )

    # Auto-lapse any past pending requests
    auto_lapse_pending_requests(db)

    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return flash_redirect(
            url="/leaves",
            message="Invalid date format. Please select valid dates.",
            category="error",
        )

    if s_date > e_date:
        return flash_redirect(
            url="/leaves",
            message="Start date cannot be later than end date.",
            category="error",
        )

    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id, LeaveType.is_active == True).first()
    if not leave_type:
        return flash_redirect(
            url="/leaves",
            message="Selected leave type is invalid or inactive.",
            category="error",
        )

    # Gender-specific eligibility check
    if not is_leave_type_applicable(leave_type, current_user.gender):
        if getattr(leave_type, "applicable_gender", "all") == "female" or leave_type.code == "ML":
            err_msg = "Maternity leave is applicable for female employees only."
        elif getattr(leave_type, "applicable_gender", "all") == "male" or leave_type.code == "PL_PAT":
            err_msg = "Paternity leave is applicable for male employees only."
        else:
            err_msg = f"{leave_type.name} is not applicable for your profile."
        return flash_redirect(
            url="/leaves",
            message=err_msg,
            category="error",
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

    # Strict Quota Enforcement
    is_lwp_unlimited = (leave_type.code == "LWP" and not leave_type.is_paid and leave_type.default_days_per_year == 0.0 and (balance.total_allocated if balance else 0.0) == 0.0)
    
    if not is_lwp_unlimited:
        avail_days = balance.remaining_days if balance else 0.0
        if avail_days < total_days:
            err_msg = f"Insufficient leave balance for {leave_type.name}. You have {avail_days:g} day(s) remaining in your quota, but requested {total_days:g} day(s)."
            return flash_redirect(
                url="/leaves",
                message=err_msg,
                category="error",
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
        return flash_redirect(
            url="/leaves",
            message="You already have a leave application covering these dates.",
            category="error",
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

    return flash_redirect(
        url="/leaves",
        message=f"Leave application for {total_days} day(s) submitted successfully.",
        category="success",
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

    today = get_ist_today()
    if app.status != "pending" or app.start_date < today:
        if app.status == "lapsed" or app.start_date < today:
            if app.status == "pending":
                auto_lapse_pending_requests(db)
            return flash_redirect(
                url="/leaves?tab=approvals",
                message="This leave application has lapsed (scheduled start date has passed) and cannot be approved.",
                category="error",
            )
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="This application has already been processed.",
            category="error",
        )

    # 6-Tier Corporate Hierarchy Authorization Enforcement
    if not can_user_approve_request(current_user, app.employee):
        raise HTTPException(status_code=403, detail="Not authorized to approve this request under corporate hierarchy.")

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

    return flash_redirect(
        url="/leaves?tab=approvals",
        message=f"Leave application for {app.employee.name} approved.",
        category="success",
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
        if app.status == "lapsed":
            return flash_redirect(
                url="/leaves?tab=approvals",
                message="This leave application has already lapsed.",
                category="error",
            )
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="This application has already been processed.",
            category="error",
        )

    # 6-Tier Corporate Hierarchy Authorization Enforcement
    if not can_user_approve_request(current_user, app.employee):
        raise HTTPException(status_code=403, detail="Not authorized to decline this request under corporate hierarchy.")

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

    return flash_redirect(
        url="/leaves?tab=approvals",
        message=f"Leave application for {app.employee.name} rejected.",
        category="success",
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

    if app.employee_id != current_user.id and current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
        raise HTTPException(status_code=403, detail="Not permitted to cancel this request")

    if app.status not in ["pending", "approved"]:
        return flash_redirect(
            url="/leaves",
            message="Only pending or approved leaves can be cancelled.",
            category="error",
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

    return flash_redirect(
        url="/leaves",
        message="Leave application cancelled successfully.",
        category="success",
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
    if current_user.role == "super_admin":
        return flash_redirect(
            url="/leaves",
            message="Super Admin accounts are exempt from submitting personal WFH requests.",
            category="error",
        )

    # Auto-lapse any past pending requests
    auto_lapse_pending_requests(db)

    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return flash_redirect(
            url="/leaves",
            message="Invalid date format. Please select valid dates.",
            category="error",
        )

    if s_date > e_date:
        return flash_redirect(
            url="/leaves",
            message="Start date cannot be later than end date.",
            category="error",
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
        return flash_redirect(
            url="/leaves",
            message="You already have a WFH request covering these dates.",
            category="error",
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

    return flash_redirect(
        url="/leaves",
        message=f"WFH request for {total_days} day(s) submitted successfully.",
        category="success",
    )


@router.post("/wfh/allocate")
async def allocate_wfh(
    request: Request,
    background_tasks: BackgroundTasks,
    start_date: str = Form(...),
    end_date: str = Form(...),
    target_type: str = Form("all"),            # "all", "department", "individual"
    employee_id: Optional[int] = Form(None),
    department_id: Optional[int] = Form(None),
    is_half_day: bool = Form(False),
    half_day_session: Optional[str] = Form(None),
    reason: str = Form("Direct WFH Allocation by Management"),
    send_email: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Directly allocates WFH for All Staff, a Department, or an Individual (Instant Auto-Approval)."""
    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="Invalid date format. Please provide valid dates.",
            category="error",
        )

    if s_date > e_date:
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="Start date cannot be after end date.",
            category="error",
        )

    total_days = calculate_leave_days(s_date, e_date, is_half_day if s_date == e_date else False)

    # 1. Resolve target employees
    target_employees: List[Employee] = []

    if target_type == "individual":
        if not employee_id:
            return flash_redirect(url="/leaves?tab=approvals", message="Please select an employee.", category="error")
        target_emp = db.query(Employee).filter(Employee.id == employee_id, Employee.is_active == True).first()
        if not target_emp:
            return flash_redirect(url="/leaves?tab=approvals", message="Selected employee not found.", category="error")
        if current_user.role == "manager":
            if (
                not current_user.department_id
                or target_emp.department_id != current_user.department_id
                or target_emp.role in ["super_admin", "admin", "hr", "hr_admin"]
            ):
                raise HTTPException(status_code=403, detail="Not authorized to allocate WFH for this employee.")
        target_employees = [target_emp]

    elif target_type == "department":
        if not department_id:
            return flash_redirect(url="/leaves?tab=approvals", message="Please select a department.", category="error")
        if current_user.role == "manager" and department_id != current_user.department_id:
            raise HTTPException(status_code=403, detail="Managers can only allocate WFH to their assigned department.")
        target_employees = db.query(Employee).filter(
            Employee.department_id == department_id,
            Employee.is_active == True,
            Employee.role != "admin"
        ).all()

    else:  # "all"
        if current_user.role == "manager":
            target_employees = db.query(Employee).filter(
                Employee.department_id == current_user.department_id,
                Employee.is_active == True,
                Employee.role != "admin"
            ).all()
        else:
            target_employees = db.query(Employee).filter(
                Employee.is_active == True,
                Employee.role != "admin"
            ).all()

    if not target_employees:
        return flash_redirect(url="/leaves?tab=approvals", message="No active employees found for this selection.", category="error")

    allocated_count = 0
    now_ist = get_ist_now()

    for emp in target_employees:
        # Check if already has overlapping approved WFH
        existing_wfh = db.query(WfhRequest).filter(
            WfhRequest.employee_id == emp.id,
            WfhRequest.status == "approved",
            WfhRequest.start_date <= e_date,
            WfhRequest.end_date >= s_date,
        ).first()

        if existing_wfh:
            continue

        wfh = WfhRequest(
            employee_id=emp.id,
            start_date=s_date,
            end_date=e_date,
            total_days=total_days,
            is_half_day=is_half_day if s_date == e_date else False,
            half_day_session=half_day_session if (is_half_day and s_date == e_date) else None,
            reason=reason.strip(),
            status="approved",
            is_direct_allocation=True,
            reviewed_by_id=current_user.id,
            reviewed_at=now_ist,
        )
        db.add(wfh)
        allocated_count += 1

        if send_email and emp.email:
            background_tasks.add_task(
                send_wfh_status_email,
                to_email=emp.email,
                recipient_name=emp.name,
                start_date=str(s_date),
                end_date=str(e_date),
                total_days=total_days,
                status="allocated",
                reason=reason.strip(),
                reviewer_remarks=f"Allocated by {current_user.name}",
            )

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="WFH_BULK_ALLOCATION",
        entity="WfhRequest",
        entity_id=current_user.id,
        old_value=target_type,
        new_value=f"Allocated WFH to {allocated_count} employee(s) ({s_date} to {e_date}): {reason[:100]}",
    )
    db.add(audit)
    db.commit()

    date_label = str(s_date) if s_date == e_date else f"{s_date} to {e_date}"
    return flash_redirect(
        url="/leaves?tab=approvals",
        message=f"WFH allocated to {allocated_count} employee(s) ({date_label}).",
        category="success",
    )


@router.post("/bulk-grant")
async def bulk_grant_leave(
    request: Request,
    background_tasks: BackgroundTasks,
    leave_type_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    target_type: str = Form("all"),            # "all", "department", "individual"
    employee_id: Optional[int] = Form(None),
    department_id: Optional[int] = Form(None),
    is_half_day: bool = Form(False),
    half_day_session: Optional[str] = Form(None),
    deduct_quota: bool = Form(False),          # Whether to deduct from leave quota
    reason: str = Form("Direct Leave Grant by Management"),
    send_email: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Directly grants and auto-approves a Leave Day/Period for All Staff, a Department, or an Individual."""
    try:
        s_date = datetime.datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        e_date = datetime.datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="Invalid date format. Please provide valid dates.",
            category="error",
        )

    if s_date > e_date:
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="Start date cannot be after end date.",
            category="error",
        )

    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id, LeaveType.is_active == True).first()
    if not leave_type:
        return flash_redirect(url="/leaves?tab=approvals", message="Invalid or inactive leave type.", category="error")

    total_days = calculate_leave_days(s_date, e_date, is_half_day if s_date == e_date else False)
    now_ist = get_ist_now()

    # 1. Resolve target employees
    target_employees: List[Employee] = []

    if target_type == "individual":
        if not employee_id:
            return flash_redirect(url="/leaves?tab=approvals", message="Please select an employee.", category="error")
        target_emp = db.query(Employee).filter(Employee.id == employee_id, Employee.is_active == True).first()
        if not target_emp:
            return flash_redirect(url="/leaves?tab=approvals", message="Selected employee not found.", category="error")
        if current_user.role == "manager":
            if (
                not current_user.department_id
                or target_emp.department_id != current_user.department_id
                or target_emp.role in ["super_admin", "admin", "hr", "hr_admin"]
            ):
                raise HTTPException(status_code=403, detail="Not authorized to grant leave for this employee.")
        target_employees = [target_emp]

    elif target_type == "department":
        if not department_id:
            return flash_redirect(url="/leaves?tab=approvals", message="Please select a department.", category="error")
        if current_user.role == "manager" and department_id != current_user.department_id:
            raise HTTPException(status_code=403, detail="Managers can only grant leave to their assigned department.")
        target_employees = db.query(Employee).filter(
            Employee.department_id == department_id,
            Employee.is_active == True,
            Employee.role != "admin"
        ).all()

    else:  # "all"
        if current_user.role == "manager":
            target_employees = db.query(Employee).filter(
                Employee.department_id == current_user.department_id,
                Employee.is_active == True,
                Employee.role != "admin"
            ).all()
        else:
            target_employees = db.query(Employee).filter(
                Employee.is_active == True,
                Employee.role != "admin"
            ).all()

    if not target_employees:
        return flash_redirect(url="/leaves?tab=approvals", message="No active employees found for this selection.", category="error")

    granted_count = 0

    for emp in target_employees:
        # Check gender applicability (e.g. skip maternity leave for males)
        if not is_leave_type_applicable(leave_type, emp.gender):
            continue

        # Check existing approved leave overlap
        existing = db.query(LeaveApplication).filter(
            LeaveApplication.employee_id == emp.id,
            LeaveApplication.status == "approved",
            LeaveApplication.start_date <= e_date,
            LeaveApplication.end_date >= s_date,
        ).first()
        if existing:
            continue

        app = LeaveApplication(
            employee_id=emp.id,
            leave_type_id=leave_type.id,
            start_date=s_date,
            end_date=e_date,
            total_days=total_days,
            is_half_day=is_half_day if s_date == e_date else False,
            half_day_session=half_day_session if (is_half_day and s_date == e_date) else None,
            reason=reason.strip(),
            status="approved",
            reviewed_by_id=current_user.id,
            reviewed_at=now_ist,
        )
        db.add(app)
        granted_count += 1

        if deduct_quota:
            ensure_employee_leave_balances(db, emp.id, s_date.year)
            bal = db.query(LeaveBalance).filter(
                LeaveBalance.employee_id == emp.id,
                LeaveBalance.leave_type_id == leave_type.id,
                LeaveBalance.year == s_date.year,
            ).first()
            if bal:
                bal.used_days += total_days

        if send_email and emp.email:
            background_tasks.add_task(
                send_leave_status_email,
                to_email=emp.email,
                recipient_name=emp.name,
                leave_type_name=leave_type.name,
                start_date=str(s_date),
                end_date=str(e_date),
                total_days=total_days,
                status="approved",
                reason=reason.strip(),
                reviewer_remarks=f"Granted by {current_user.name}",
            )

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="LEAVE_BULK_GRANT",
        entity="LeaveApplication",
        entity_id=current_user.id,
        old_value=target_type,
        new_value=f"Granted {leave_type.name} to {granted_count} employee(s) ({s_date} to {e_date}): {reason[:100]}",
    )
    db.add(audit)
    db.commit()

    date_label = str(s_date) if s_date == e_date else f"{s_date} to {e_date}"
    return flash_redirect(
        url="/leaves?tab=approvals",
        message=f"{leave_type.name} granted to {granted_count} employee(s) ({date_label}).",
        category="success",
    )


@router.post("/balances/bulk-allocate")
async def bulk_allocate_quota(
    request: Request,
    leave_type_id: int = Form(...),
    year: int = Form(...),
    target_type: str = Form("all"),            # "all", "department"
    department_id: Optional[int] = Form(None),
    allocation_mode: str = Form("set_fixed"),  # "set_fixed" or "add_bonus"
    days: float = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Bulk sets or updates annual leave quota balances for All Staff or a Department (Admin Only)."""
    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id, LeaveType.is_active == True).first()
    if not leave_type:
        return flash_redirect(url="/leaves", message="Invalid or inactive leave type.", category="error")

    if days < 0:
        return flash_redirect(url="/leaves", message="Days cannot be negative.", category="error")

    if target_type == "department" and department_id:
        target_employees = db.query(Employee).filter(
            Employee.department_id == department_id,
            Employee.is_active == True,
            Employee.role != "admin"
        ).all()
    else:
        target_employees = db.query(Employee).filter(
            Employee.is_active == True,
            Employee.role != "admin"
        ).all()

    if not target_employees:
        return flash_redirect(url="/leaves", message="No active employees found to allocate.", category="error")

    updated_count = 0
    for emp in target_employees:
        if not is_leave_type_applicable(leave_type, emp.gender):
            continue

        bal = db.query(LeaveBalance).filter(
            LeaveBalance.employee_id == emp.id,
            LeaveBalance.leave_type_id == leave_type.id,
            LeaveBalance.year == year,
        ).first()

        if not bal:
            bal = LeaveBalance(
                employee_id=emp.id,
                leave_type_id=leave_type.id,
                year=year,
                total_allocated=days if allocation_mode == "set_fixed" else (leave_type.default_days_per_year + days),
                used_days=0.0,
                pending_days=0.0,
            )
            db.add(bal)
        else:
            if allocation_mode == "set_fixed":
                bal.total_allocated = days
            else:
                bal.total_allocated += days

        updated_count += 1

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="LEAVE_QUOTA_BULK_ALLOCATE",
        entity="LeaveBalance",
        entity_id=current_user.id,
        old_value=f"mode={allocation_mode}",
        new_value=f"Updated {leave_type.name} quota to/by {days}d for {updated_count} employees (Year {year})",
    )
    db.add(audit)
    db.commit()

    return flash_redirect(
        url="/leaves",
        message=f"Updated {leave_type.name} quota for {updated_count} employee(s) (Year {year}).",
        category="success",
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

    today = get_ist_today()
    if wfh.status != "pending" or wfh.start_date < today:
        if wfh.status == "lapsed" or wfh.start_date < today:
            if wfh.status == "pending":
                auto_lapse_pending_requests(db)
            return flash_redirect(
                url="/leaves?tab=approvals",
                message="This WFH request has lapsed (scheduled start date has passed) and cannot be approved.",
                category="error",
            )
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="This WFH request has already been processed.",
            category="error",
        )

    # 6-Tier Corporate Hierarchy Authorization Enforcement
    if not can_user_approve_request(current_user, wfh.employee):
        raise HTTPException(status_code=403, detail="Not authorized to approve this WFH request under corporate hierarchy.")

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

    return flash_redirect(
        url="/leaves?tab=approvals",
        message=f"WFH request for {wfh.employee.name} approved.",
        category="success",
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
        if wfh.status == "lapsed":
            return flash_redirect(
                url="/leaves?tab=approvals",
                message="This WFH request has already lapsed.",
                category="error",
            )
        return flash_redirect(
            url="/leaves?tab=approvals",
            message="This WFH request has already been processed.",
            category="error",
        )

    # 6-Tier Corporate Hierarchy Authorization Enforcement
    if not can_user_approve_request(current_user, wfh.employee):
        raise HTTPException(status_code=403, detail="Not authorized to decline this WFH request under corporate hierarchy.")

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

    return flash_redirect(
        url="/leaves?tab=approvals",
        message=f"WFH request for {wfh.employee.name} rejected.",
        category="success",
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

    if wfh.employee_id != current_user.id and current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
        raise HTTPException(status_code=403, detail="Not permitted to cancel this request")

    wfh.status = "cancelled"
    db.commit()

    return flash_redirect(
        url="/leaves",
        message="WFH request cancelled successfully.",
        category="success",
    )


# =========================================================================
# LEAVE BALANCES QUOTA MANAGEMENT (ADMIN ONLY)
# =========================================================================

@router.post("/balances/{balance_id}/adjust")
async def adjust_leave_balance(
    balance_id: int,
    request: Request,
    total_allocated: float = Form(...),
    redirect_target: Optional[str] = Form(None),
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

    target_url = redirect_target or "/leaves?tab=team_balances"
    return flash_redirect(
        url=target_url,
        message=f"Quota updated for {bal.employee.name} ({bal.leave_type.name}).",
        category="success",
    )


# =========================================================================
# LEAVE TYPES & STATUTORY POLICIES CONFIGURATION (ADMIN ONLY)
# =========================================================================

@router.get("/types", response_class=HTMLResponse)
async def list_leave_types(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Admin configuration dashboard for dynamic Leave Types & Entitlement Policies."""
    types = db.query(LeaveType).order_by(LeaveType.is_active.desc(), LeaveType.id.asc()).all()
    selected_year = get_ist_today().year

    stats = {}
    total_active_balances = 0
    total_applications = 0

    for lt in types:
        app_count = db.query(LeaveApplication).filter(LeaveApplication.leave_type_id == lt.id).count()
        bal_records = db.query(LeaveBalance).filter(LeaveBalance.leave_type_id == lt.id, LeaveBalance.year == selected_year).all()
        total_allocated_sum = sum(b.total_allocated for b in bal_records)
        used_sum = sum(b.used_days for b in bal_records)
        
        stats[lt.id] = {
            "applications_count": app_count,
            "employees_enrolled": len(bal_records),
            "total_allocated_days": total_allocated_sum,
            "total_used_days": used_sum,
        }
        total_applications += app_count
        total_active_balances += len(bal_records)

    paid_count = sum(1 for lt in types if lt.is_paid and lt.is_active)
    unpaid_count = sum(1 for lt in types if not lt.is_paid and lt.is_active)

    return templates.TemplateResponse(
        request=request,
        name="leaves/types.html",
        context={
            "user": current_user,
            "leave_types": types,
            "stats": stats,
            "selected_year": selected_year,
            "paid_count": paid_count,
            "unpaid_count": unpaid_count,
            "total_active_balances": total_active_balances,
            "total_applications": total_applications,
        },
    )


@router.post("/types/create")
async def create_leave_type(
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    description: Optional[str] = Form(None),
    default_days_per_year: float = Form(12.0),
    is_paid: Optional[str] = Form("on"),
    color_code: str = Form("#008080"),
    applicable_gender: str = Form("all"),
    auto_allocate_existing: Optional[str] = Form("on"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Creates a new dynamic leave type with optional instant quota allocation."""
    clean_name = name.strip()
    clean_code = re.sub(r"[^A-Za-z0-9_]", "_", code.strip().upper()).strip("_")
    
    if not clean_code:
        clean_code = re.sub(r"[^A-Za-z0-9_]", "_", clean_name.upper())[:10]

    # Validate uniqueness of code
    existing = db.query(LeaveType).filter(LeaveType.code == clean_code).first()
    if existing:
        return flash_redirect(
            url="/leaves/types",
            message=f"Leave type code '{clean_code}' is already in use. Please choose a unique code.",
            category="error",
        )

    is_paid_bool = is_paid in ["on", "true", "1", "True", True] if is_paid else False
    if applicable_gender not in ["all", "female", "male"]:
        applicable_gender = "all"

    new_leave_type = LeaveType(
        name=clean_name,
        code=clean_code,
        description=description.strip() if description else None,
        default_days_per_year=max(0.0, float(default_days_per_year)),
        is_paid=is_paid_bool,
        color_code=color_code.strip() or "#008080",
        applicable_gender=applicable_gender,
        is_active=True,
    )
    db.add(new_leave_type)
    db.flush()

    # Automatically provision quota for applicable active employees if requested
    allocated_count = 0
    if auto_allocate_existing in ["on", "true", "1", "True", True]:
        current_year = get_ist_today().year
        active_employees = db.query(Employee).filter(Employee.is_active == True, Employee.role != "admin").all()
        for emp in active_employees:
            if is_leave_type_applicable(new_leave_type, emp.gender):
                bal = db.query(LeaveBalance).filter(
                    LeaveBalance.employee_id == emp.id,
                    LeaveBalance.leave_type_id == new_leave_type.id,
                    LeaveBalance.year == current_year,
                ).first()
                if not bal:
                    bal = LeaveBalance(
                        employee_id=emp.id,
                        leave_type_id=new_leave_type.id,
                        year=current_year,
                        total_allocated=new_leave_type.default_days_per_year,
                        used_days=0.0,
                        pending_days=0.0,
                    )
                    db.add(bal)
                    allocated_count += 1

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_LEAVE_TYPE",
        entity="LeaveType",
        entity_id=new_leave_type.id,
        new_value=f"Created leave type: {new_leave_type.name} ({new_leave_type.code}, {new_leave_type.default_days_per_year}d, gender={new_leave_type.applicable_gender}, allocated_to={allocated_count} staff)",
    )
    db.add(audit)
    db.commit()

    msg = f"Leave type '{new_leave_type.name}' created successfully"
    if allocated_count > 0:
        msg += f" and provisioned for {allocated_count} active employee(s)"
    return flash_redirect(
        url="/leaves/types",
        message=f"{msg}.",
        category="success",
    )


@router.post("/types/{type_id}/edit")
async def edit_leave_type(
    type_id: int,
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    description: Optional[str] = Form(None),
    default_days_per_year: float = Form(...),
    is_paid: Optional[str] = Form(None),
    color_code: str = Form("#008080"),
    applicable_gender: str = Form("all"),
    is_active: Optional[str] = Form(None),
    sync_balances: Optional[str] = Form("on"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Updates an existing dynamic leave type and propagates changes to active employees."""
    leave_type = db.query(LeaveType).filter(LeaveType.id == type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")

    clean_name = name.strip()
    clean_code = re.sub(r"[^A-Za-z0-9_]", "_", code.strip().upper()).strip("_")
    
    # Check code collision if code changed
    if clean_code != leave_type.code:
        existing = db.query(LeaveType).filter(LeaveType.code == clean_code, LeaveType.id != type_id).first()
        if existing:
            return flash_redirect(
                url="/leaves/types",
                message=f"Leave type code '{clean_code}' already in use.",
                category="error",
            )

    is_paid_bool = is_paid in ["on", "true", "1", "True", True] if is_paid else False
    is_active_bool = is_active in ["on", "true", "1", "True", True] if is_active else False
    if applicable_gender not in ["all", "female", "male"]:
        applicable_gender = "all"

    old_info = f"{leave_type.name} ({leave_type.code}, {leave_type.default_days_per_year}d, active={leave_type.is_active})"

    leave_type.name = clean_name
    leave_type.code = clean_code
    leave_type.description = description.strip() if description else None
    leave_type.default_days_per_year = max(0.0, float(default_days_per_year))
    leave_type.is_paid = is_paid_bool
    leave_type.color_code = color_code.strip() or "#008080"
    leave_type.applicable_gender = applicable_gender
    leave_type.is_active = is_active_bool

    # Propagate / sync to employee balances if enabled
    current_year = get_ist_today().year
    sync_result = None
    if sync_balances in ["on", "true", "1", "True", True]:
        sync_result = sync_all_leave_quotas_with_policies(db, current_year, leave_type_id=type_id)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="EDIT_LEAVE_TYPE",
        entity="LeaveType",
        entity_id=leave_type.id,
        old_value=old_info,
        new_value=f"{leave_type.name} ({leave_type.code}, {leave_type.default_days_per_year}d, active={leave_type.is_active})",
    )
    db.add(audit)
    db.commit()

    msg = f"Leave type '{leave_type.name}' updated successfully"
    if sync_result:
        msg += f" (synced quota to {leave_type.default_days_per_year}d for {sync_result['updated_count']} employee record(s))"
    return flash_redirect(
        url="/leaves/types",
        message=f"{msg}.",
        category="success",
    )


@router.post("/types/sync-quotas")
async def sync_all_leave_quotas(
    request: Request,
    year: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Admin action to immediately synchronize all employee leave quotas with active policy defaults."""
    target_year = year or get_ist_today().year
    res = sync_all_leave_quotas_with_policies(db, target_year)
    
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="SYNC_LEAVE_QUOTAS",
        entity="LeaveBalance",
        entity_id=current_user.id,
        new_value=f"Synchronized quotas with leave policies for {res['employees_count']} employees for Year {target_year} ({res['updated_count']} balance updates, {res['cleaned_count']} obsolete balances cleaned)",
    )
    db.add(audit)
    db.commit()

    return flash_redirect(
        url="/leaves/types",
        message=f"Successfully synchronized leave quotas with policy defaults for {res['employees_count']} employees (Year {target_year}).",
        category="success",
    )


@router.post("/types/{type_id}/delete")
async def delete_leave_type(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Safely deletes or deactivates a dynamic leave type."""
    leave_type = db.query(LeaveType).filter(LeaveType.id == type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")

    # Check if any leave applications exist
    apps_count = db.query(LeaveApplication).filter(LeaveApplication.leave_type_id == type_id).count()

    if apps_count > 0:
        # Cannot hard-delete without breaking employee attendance & leave history
        leave_type.is_active = False
        db.commit()

        audit = AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="DEACTIVATE_LEAVE_TYPE",
            entity="LeaveType",
            entity_id=type_id,
            new_value=f"Deactivated {leave_type.name} (has {apps_count} historical applications)",
        )
        db.add(audit)
        db.commit()

        return flash_redirect(
            url="/leaves/types",
            message=f"Leave type '{leave_type.name}' has {apps_count} historical application(s) and was safely deactivated (archived) to preserve audit history.",
            category="success",
        )

    # No applications exist: safe to delete balances and leave type permanently
    lt_name = leave_type.name
    db.query(LeaveBalance).filter(LeaveBalance.leave_type_id == type_id).delete(synchronize_session=False)
    db.delete(leave_type)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="DELETE_LEAVE_TYPE",
        entity="LeaveType",
        entity_id=type_id,
        old_value=f"Permanently deleted unused leave type: {lt_name}",
    )
    db.add(audit)
    db.commit()

    return flash_redirect(
        url="/leaves/types",
        message=f"Leave type '{lt_name}' was permanently deleted.",
        category="success",
    )


@router.post("/types/{type_id}/toggle-status")
async def toggle_leave_type_status(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    """Quick toggle active / inactive status."""
    leave_type = db.query(LeaveType).filter(LeaveType.id == type_id).first()
    if not leave_type:
        raise HTTPException(status_code=404, detail="Leave type not found")

    leave_type.is_active = not leave_type.is_active
    status_str = "activated" if leave_type.is_active else "deactivated"

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="TOGGLE_LEAVE_TYPE_STATUS",
        entity="LeaveType",
        entity_id=type_id,
        new_value=f"{leave_type.name} {status_str}",
    )
    db.add(audit)
    db.commit()

    return flash_redirect(
        url="/leaves/types",
        message=f"Leave type '{leave_type.name}' {status_str} successfully.",
        category="success",
    )


# =========================================================================
# LEAVES & BALANCES EXCEL EXPORTS
# =========================================================================

@router.get("/export-excel")
async def export_leaves_ledger(
    year: Optional[int] = None,
    status: Optional[str] = "all",
    type_id: Optional[int] = None,
    subtab: Optional[str] = "leaves",
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Exports leave applications or WFH requests ledger to Excel matching active filters."""
    today = get_ist_today()
    sel_year = year or today.year

    if subtab == "wfh":
        query = db.query(WfhRequest).join(Employee, WfhRequest.employee_id == Employee.id)
        if current_user.role in ["employee", "intern"]:
            query = query.filter(WfhRequest.employee_id == current_user.id)
        elif current_user.role == "manager":
            query = query.filter(
                or_(
                    WfhRequest.employee_id == current_user.id,
                    and_(
                        Employee.department_id == current_user.department_id,
                        Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
                    )
                )
            )

        if sel_year:
            query = query.filter(extract("year", WfhRequest.start_date) == sel_year)
        if status and status.strip() and status.lower() != "all":
            query = query.filter(WfhRequest.status == status.strip().lower())

        records = query.order_by(WfhRequest.start_date.desc()).all()
    else:
        query = db.query(LeaveApplication).join(Employee, LeaveApplication.employee_id == Employee.id)
        if current_user.role in ["employee", "intern"]:
            query = query.filter(LeaveApplication.employee_id == current_user.id)
        elif current_user.role == "manager":
            query = query.filter(
                or_(
                    LeaveApplication.employee_id == current_user.id,
                    and_(
                        Employee.department_id == current_user.department_id,
                        Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
                    )
                )
            )

        if sel_year:
            query = query.filter(extract("year", LeaveApplication.start_date) == sel_year)
        if status and status.strip() and status.lower() != "all":
            query = query.filter(LeaveApplication.status == status.strip().lower())
        if type_id and type_id > 0:
            query = query.filter(LeaveApplication.leave_type_id == type_id)

        records = query.order_by(LeaveApplication.start_date.desc()).all()

    company = db.query(Company).first()
    return export_leaves_excel(records, company, year=sel_year, status_filter=status)


@router.get("/balances/export-excel")
async def export_leave_balances_spreadsheet(
    year: Optional[int] = None,
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Exports staff annual leave quotas and balances."""
    today = get_ist_today()
    sel_year = year or today.year

    query = db.query(LeaveBalance).join(Employee, LeaveBalance.employee_id == Employee.id).filter(
        LeaveBalance.year == sel_year,
        Employee.is_active == True,
        Employee.role != "super_admin"
    )

    if current_user.role == "manager":
        query = query.filter(Employee.department_id == current_user.department_id)
    elif dept_id and dept_id > 0:
        query = query.filter(Employee.department_id == dept_id)

    balances = query.order_by(Employee.name.asc()).all()
    company = db.query(Company).first()
    return export_leave_balances_excel(balances, company, year=sel_year)
