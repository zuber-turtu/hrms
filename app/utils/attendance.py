import datetime
from sqlalchemy.orm import Session
from fastapi import Request
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.utils.timezone import get_ist_today


def update_attendance_request_state(db: Session, user: Employee, request: Request) -> None:
    """
    Computes today's active check-in and accumulated worked seconds for the given user,
    updating the request.state object for templates and HTMX partials.
    """
    today = get_ist_today()
    today_logs = (
        db.query(Attendance)
        .filter(Attendance.employee_id == user.id, Attendance.date == today)
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

    if active_checkin:
        request.state.is_checked_in = True
        request.state.active_check_in = active_checkin
        request.state.active_check_in_iso = f"{active_checkin.strftime('%Y-%m-%dT%H:%M:%S')}+05:30"
        request.state.accumulated_seconds = int(accumulated)
    else:
        request.state.is_checked_in = False
        request.state.last_check_out = last_out
        request.state.accumulated_seconds = int(accumulated)
        hrs = int(accumulated // 3600)
        mins = int((accumulated % 3600) // 60)
        secs = int(accumulated % 60)
        request.state.accumulated_time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
