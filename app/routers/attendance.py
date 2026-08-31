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
    if current_user.role == "employee":
        logs = (
            db.query(Attendance)
            .filter(Attendance.employee_id == current_user.id)
            .order_by(Attendance.date.desc())
            .all()
        )
    else:
        logs = db.query(Attendance).order_by(Attendance.date.desc()).all()

    return templates.TemplateResponse(
        request, "attendance/log.html", {"user": current_user, "logs": logs}
    )


@router.post("/check-in")
async def check_in(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = datetime.date.today()
    log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
    ).first()

    if not log:
        log = Attendance(
            employee_id=current_user.id,
            date=today,
            check_in=datetime.datetime.now(),
        )
        db.add(log)
        db.commit()

    return RedirectResponse(url="/attendance", status_code=302)


@router.post("/check-out")
async def check_out(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = datetime.date.today()
    log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
    ).first()

    if log and not log.check_out:
        log.check_out = datetime.datetime.now()
        db.commit()

    return RedirectResponse(url="/attendance", status_code=302)


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
