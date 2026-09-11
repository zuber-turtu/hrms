from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker

from app.utils.timezone import get_ist_today, get_ist_now
from app.utils.security import get_safe_redirect
from app.utils.attendance import update_attendance_request_state

router = APIRouter(prefix="/attendance")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["admin", "hr_admin", "manager"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def attendance_log(
    request: Request,
    q: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    from collections import defaultdict
    
    if current_user.role in ["employee", "intern"]:
        raw_logs = (
            db.query(Attendance)
            .filter(Attendance.employee_id == current_user.id)
            .order_by(Attendance.date.desc(), Attendance.check_in.asc())
            .all()
        )
    elif current_user.role == "manager":
        # Scoped to own department subordinates
        raw_logs = (
            db.query(Attendance)
            .join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.department_id == current_user.department_id,
                Employee.role.notin_(["admin", "hr_admin"])
            )
            .order_by(Attendance.date.desc(), Attendance.check_in.asc())
            .all()
        )
    else:
        raw_logs = db.query(Attendance).order_by(Attendance.date.desc(), Attendance.check_in.asc()).all()

    # Group raw logs by (date, employee_id)
    grouped = defaultdict(list)
    for log in raw_logs:
        grouped[(log.date, log.employee_id)].append(log)

    logs_data = []
    today = get_ist_today()
    now_ist = get_ist_now()
    for (date, emp_id), group_logs in grouped.items():
        employee = group_logs[0].employee
        
        total_seconds = 0
        sessions = []
        is_overridden = False
        override_reason = ""
        is_missed = False
        
        for log in group_logs:
            if log.is_overridden:
                is_overridden = True
                override_reason = log.override_reason
                
            start = log.check_in
            if log.check_out:
                end = log.check_out
                out_str = log.check_out.strftime('%I:%M %p')
            else:
                if log.date < today:
                    end = log.check_in  # 0 duration
                    out_str = "Missed"
                    is_missed = True
                else:
                    end = now_ist
                    out_str = "Active"
            
            diff = (end - start).total_seconds()
            total_seconds += max(0, diff)
            
            in_str = log.check_in.strftime('%I:%M %p')
            sessions.append(f"{in_str} - {out_str}")
            
        hrs = int(total_seconds // 3600)
        mins = int((total_seconds % 3600) // 60)
        secs = int(total_seconds % 60)
        total_active_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        
        item = {
            "id": group_logs[0].id,  # primary ID for override actions
            "date": date,
            "employee": employee,
            "sessions": ", ".join(sessions),
            "total_active": f"{total_active_str} (Missed)" if is_missed else total_active_str,
            "is_overridden": is_overridden,
            "override_reason": override_reason,
            "is_missed": is_missed,
            "check_in": group_logs[0].check_in,
            "check_out": group_logs[-1].check_out
        }

        # Apply search filter (date or employee name)
        if q and q.strip():
            query_lower = q.strip().lower()
            emp_name = (employee.name or "").lower()
            date_str = str(date).lower()
            if query_lower not in emp_name and query_lower not in date_str:
                continue

        # Apply status filter
        if status and status.strip() and status.strip() != "all":
            st = status.strip().lower()
            if st == "missed" and not is_missed:
                continue
            elif st == "overridden" and not is_overridden:
                continue
            elif st == "normal" and (is_missed or is_overridden):
                continue

        logs_data.append(item)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="attendance/partials/_log_table.html",
            context={"user": current_user, "logs": logs_data}
        )

    return templates.TemplateResponse(
        request=request, name="attendance/log.html", context={"user": current_user, "logs": logs_data}
    )


@router.post("/check-in")
async def check_in(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = get_ist_today()
    # Check if there is an active check-in (check_out is None)
    active_log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.check_out == None
    ).first()

    if not active_log:
        log = Attendance(
            employee_id=current_user.id,
            date=today,
            check_in=get_ist_now(),
        )
        db.add(log)
        db.commit()

    if request.headers.get("HX-Request"):
        update_attendance_request_state(db, current_user, request)
        return templates.TemplateResponse(
            request,
            "attendance/partials/_topbar_widget.html",
            {"user": current_user}
        )

    safe_target = get_safe_redirect(request, default="/dashboard")
    return RedirectResponse(url=safe_target, status_code=302)


@router.post("/check-out")
async def check_out(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = get_ist_today()
    # Find the active check-in log to checkout
    log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.check_out == None
    ).order_by(Attendance.check_in.desc()).first()

    if log:
        log.check_out = get_ist_now()
        db.commit()

    if request.headers.get("HX-Request"):
        update_attendance_request_state(db, current_user, request)
        return templates.TemplateResponse(
            request,
            "attendance/partials/_topbar_widget.html",
            {"user": current_user}
        )

    safe_target = get_safe_redirect(request, default="/dashboard")
    return RedirectResponse(url=safe_target, status_code=302)


@router.post("/{log_id}/override")
async def override_attendance(
    log_id: int,
    request: Request,
    check_in_time: str = Form(None),
    check_out_time: str = Form(None),
    reason: str = Form("Manual HR Adjustment"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    log = db.query(Attendance).filter(Attendance.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    # Scope verification: Managers can only override records of subordinates in their own department
    if current_user.role == "manager":
        if (
            not current_user.department_id
            or log.employee.department_id != current_user.department_id
            or log.employee.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(
                status_code=403,
                detail="Operation not permitted: Managers can only adjust attendance for subordinates in their department."
            )

    old_val = f"In: {log.check_in}, Out: {log.check_out}"

    if check_in_time:
        h, m = map(int, check_in_time.split(":"))
        log.check_in = datetime.datetime.combine(log.date, datetime.time(h, m))

    if check_out_time:
        h, m = map(int, check_out_time.split(":"))
        log.check_out = datetime.datetime.combine(log.date, datetime.time(h, m))

    log.is_overridden = True
    log.override_reason = reason

    new_val = f"In: {log.check_in}, Out: {log.check_out}"

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="ATTENDANCE_OVERRIDE",
        entity="Attendance",
        entity_id=log.id,
        old_value=old_val,
        new_value=new_val,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/attendance", status_code=302)
