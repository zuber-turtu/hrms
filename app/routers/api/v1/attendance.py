from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from collections import defaultdict
import datetime

from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.utils.timezone import get_ist_today, get_ist_now
from app.schemas.attendance import (
    AttendanceStatusOut,
    AttendanceCheckInRequest,
    AttendanceLogItem,
    AttendanceOverrideRequest,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])
allow_hr_admin = RoleChecker(["admin", "hr_admin", "manager"])


@router.get("/status", response_model=AttendanceStatusOut)
async def api_get_attendance_status(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Get the current user's active attendance shift status and total accumulated working time today.
    """
    today = get_ist_today()
    today_logs = (
        db.query(Attendance)
        .filter(Attendance.employee_id == current_user.id, Attendance.date == today)
        .order_by(Attendance.check_in.asc())
        .all()
    )

    accumulated = 0.0
    active_checkin = None
    last_out = None

    for log in today_logs:
        if log.check_in and log.check_out:
            diff = (log.check_out - log.check_in).total_seconds()
            if diff > 0:
                accumulated += diff
            last_out = log.check_out
        elif log.check_in and not log.check_out:
            active_checkin = log.check_in

    hrs = int(accumulated // 3600)
    mins = int((accumulated % 3600) // 60)
    secs = int(accumulated % 60)
    time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

    return AttendanceStatusOut(
        is_checked_in=active_checkin is not None,
        active_check_in=active_checkin,
        last_check_out=last_out,
        accumulated_seconds=int(accumulated),
        accumulated_time_str=time_str,
    )


@router.post("/check-in", response_model=AttendanceStatusOut)
async def api_check_in(
    payload: Optional[AttendanceCheckInRequest] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Clock in for today's work shift (supports mobile punch timestamps).
    """
    today = get_ist_today()
    active_log = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == current_user.id,
            Attendance.date == today,
            Attendance.check_out == None,
        )
        .first()
    )

    if not active_log:
        log = Attendance(
            employee_id=current_user.id,
            date=today,
            check_in=get_ist_now(),
        )
        db.add(log)
        db.commit()

    return await api_get_attendance_status(db, current_user)


@router.post("/check-out", response_model=AttendanceStatusOut)
async def api_check_out(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Clock out of the active work shift.
    """
    today = get_ist_today()
    log = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == current_user.id,
            Attendance.date == today,
            Attendance.check_out == None,
        )
        .order_by(Attendance.check_in.desc())
        .first()
    )

    if log:
        log.check_out = get_ist_now()
        db.commit()

    return await api_get_attendance_status(db, current_user)


@router.get("/logs", response_model=List[AttendanceLogItem])
async def api_get_attendance_logs(
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    employee_id: Optional[int] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Retrieve attendance logs. Standard employees see only their own logs; Managers and Admins can query team records.
    """
    query = db.query(Attendance)

    if current_user.role in ["employee", "intern"]:
        query = query.filter(Attendance.employee_id == current_user.id)
    elif current_user.role == "manager":
        query = query.join(Employee, Attendance.employee_id == Employee.id).filter(
            Employee.department_id == current_user.department_id,
            Employee.role.notin_(["admin", "hr_admin"]),
        )
        if employee_id:
            query = query.filter(Attendance.employee_id == employee_id)
    else:
        if employee_id:
            query = query.filter(Attendance.employee_id == employee_id)

    raw_logs = query.order_by(Attendance.date.desc(), Attendance.check_in.asc()).all()

    grouped = defaultdict(list)
    for log in raw_logs:
        if month and log.date.month != month:
            continue
        if year and log.date.year != year:
            continue
        grouped[(log.date, log.employee_id)].append(log)

    logs_data = []
    today = get_ist_today()
    now_ist = get_ist_now()

    for (date_val, emp_id), group_logs in grouped.items():
        employee = group_logs[0].employee
        if not employee:
            continue

        total_seconds = 0.0
        sessions = []
        is_overridden = False
        override_reason = None
        is_missed = False

        for log in group_logs:
            if log.is_overridden:
                is_overridden = True
                override_reason = log.override_reason

            start = log.check_in
            if log.check_out:
                end = log.check_out
                out_str = log.check_out.strftime("%I:%M %p")
            else:
                if log.date < today:
                    end = log.check_in
                    out_str = "Missed"
                    is_missed = True
                else:
                    end = now_ist
                    out_str = "Active"

            diff = (end - start).total_seconds()
            total_seconds += max(0.0, diff)
            in_str = log.check_in.strftime("%I:%M %p")
            sessions.append(f"{in_str} - {out_str}")

        hrs = int(total_seconds // 3600)
        mins = int((total_seconds % 3600) // 60)
        secs = int(total_seconds % 60)
        total_active_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

        # Filters
        if q and q.strip():
            ql = q.strip().lower()
            if ql not in (employee.name or "").lower() and ql not in str(date_val):
                continue

        if status_filter and status_filter.strip() != "all":
            sf = status_filter.strip().lower()
            if sf == "missed" and not is_missed:
                continue
            elif sf == "overridden" and not is_overridden:
                continue
            elif sf == "normal" and (is_missed or is_overridden):
                continue

        logs_data.append(
            AttendanceLogItem(
                id=group_logs[0].id,
                date=date_val,
                employee_id=emp_id,
                employee_name=employee.name,
                employee_role=employee.role,
                department_name=employee.department.name if employee.department else "General",
                sessions=", ".join(sessions),
                total_active=f"{total_active_str} (Missed)" if is_missed else total_active_str,
                is_missed=is_missed,
                is_overridden=is_overridden,
                override_reason=override_reason,
                check_in=group_logs[0].check_in,
                check_out=group_logs[-1].check_out,
            )
        )

    return logs_data


@router.post("/{log_id}/override")
async def api_override_attendance(
    log_id: int,
    payload: AttendanceOverrideRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Manually adjust attendance punch in/out timestamps (Managers and Admins).
    """
    log = db.query(Attendance).filter(Attendance.id == log_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found",
        )

    # Manager Department Scoping
    if current_user.role == "manager":
        if (
            not current_user.department_id
            or log.employee.department_id != current_user.department_id
            or log.employee.role in ["admin", "hr_admin"]
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted: Managers can only adjust attendance for subordinates in their department.",
            )

    old_val = f"In: {log.check_in}, Out: {log.check_out}"

    if payload.check_in_time:
        try:
            h, m = map(int, payload.check_in_time.split(":"))
            log.check_in = datetime.datetime.combine(log.date, datetime.time(h, m))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid check_in_time format. Use HH:MM",
            )

    if payload.check_out_time:
        try:
            h, m = map(int, payload.check_out_time.split(":"))
            log.check_out = datetime.datetime.combine(log.date, datetime.time(h, m))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid check_out_time format. Use HH:MM",
            )

    log.is_overridden = True
    log.override_reason = payload.reason

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

    return {"message": "Attendance record adjusted successfully.", "record_id": log_id}
