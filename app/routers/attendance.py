from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import datetime

from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker

router = APIRouter(prefix="/attendance")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["super_admin", "hr_admin", "manager"])


@router.get("/", response_class=HTMLResponse)
async def attendance_log(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    from collections import defaultdict
    
    if current_user.role == "employee":
        raw_logs = (
            db.query(Attendance)
            .filter(Attendance.employee_id == current_user.id)
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
    today = datetime.date.today()
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
                    end = datetime.datetime.now()
                    out_str = "Active"
            
            diff = (end - start).total_seconds()
            total_seconds += max(0, diff)
            
            in_str = log.check_in.strftime('%I:%M %p')
            sessions.append(f"{in_str} - {out_str}")
            
        hrs = int(total_seconds // 3600)
        mins = int((total_seconds % 3600) // 60)
        secs = int(total_seconds % 60)
        total_active_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        
        logs_data.append({
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
        })

    return templates.TemplateResponse(
        request, "attendance/log.html", {"user": current_user, "logs": logs_data}
    )


@router.post("/check-in")
async def check_in(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = datetime.date.today()
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
            check_in=datetime.datetime.now(),
        )
        db.add(log)
        db.commit()

    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=referer, status_code=302)


@router.post("/check-out")
async def check_out(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = datetime.date.today()
    # Find the active check-in log to checkout
    log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.check_out == None
    ).order_by(Attendance.check_in.desc()).first()

    if log:
        log.check_out = datetime.datetime.now()
        db.commit()

    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(url=referer, status_code=302)


@router.post("/{log_id}/override")
async def override_attendance(
    log_id: int,
    request: Request,
    check_in_time: str = Form(None),
    check_out_time: str = Form(None),
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    log = db.query(Attendance).filter(Attendance.id == log_id).first()
    if log:
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
