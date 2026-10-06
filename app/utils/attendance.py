import datetime
from sqlalchemy.orm import Session
from fastapi import Request
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.company import Company
from app.utils.timezone import get_ist_today, get_ist_now


def update_attendance_request_state(db: Session, user: Employee, request: Request) -> None:
    """
    Computes today's active check-in and accumulated worked seconds for the given user,
    updating the request.state object for templates and HTMX partials.
    """
    if user and user.role == "super_admin":
        request.state.is_checked_in = False
        request.state.active_check_in = None
        request.state.active_check_in_iso = ""
        request.state.last_check_out = None
        request.state.accumulated_seconds = 0
        request.state.accumulated_time_str = "00:00:00"
        request.state.is_lunch_window = False
        request.state.is_on_lunch_break = False
        request.state.lunch_start_str = "01:00 PM"
        request.state.lunch_end_str = "02:00 PM"
        request.state.lunch_break_hours = 1.0
        return

    today = get_ist_today()
    now_ist = get_ist_now()
    now_time = now_ist.time()

    company = db.query(Company).first()
    lunch_start_raw = company.lunch_start_time if company and company.lunch_start_time else "13:00"
    lunch_end_raw = company.lunch_end_time if company and company.lunch_end_time else "14:00"
    lunch_hours = company.lunch_break_hours if company and company.lunch_break_hours is not None else 1.0

    try:
        sh, sm = map(int, lunch_start_raw.split(":")[:2])
        lunch_start_time = datetime.time(sh, sm)
    except Exception:
        lunch_start_time = datetime.time(13, 0)

    try:
        eh, em = map(int, lunch_end_raw.split(":")[:2])
        lunch_end_time = datetime.time(eh, em)
    except Exception:
        lunch_end_time = datetime.time(14, 0)

    is_lunch_window = (lunch_start_time <= now_time <= lunch_end_time)

    today_logs = (
        db.query(Attendance)
        .filter(Attendance.employee_id == user.id, Attendance.date == today)
        .order_by(Attendance.check_in.asc())
        .all()
    )

    accumulated = 0.0
    active_checkin = None
    last_out = None
    last_out_was_lunch = False

    for log in today_logs:
        if log.check_in and log.check_out:
            diff = (log.check_out - log.check_in).total_seconds()
            if diff > 0:
                accumulated += diff
            last_out = log.check_out
            if log.override_reason and "lunch" in log.override_reason.lower():
                last_out_was_lunch = True
            else:
                last_out_was_lunch = False
        elif log.check_in and not log.check_out:
            active_checkin = log.check_in

    has_prior_punch = (len(today_logs) > 0 and any(l.check_in for l in today_logs))
    is_on_lunch_break = False
    if not active_checkin and has_prior_punch and last_out:
        if last_out_was_lunch or is_lunch_window:
            is_on_lunch_break = True

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

    request.state.is_lunch_window = is_lunch_window
    request.state.is_on_lunch_break = is_on_lunch_break
    request.state.lunch_start_str = lunch_start_time.strftime("%I:%M %p")
    request.state.lunch_end_str = lunch_end_time.strftime("%I:%M %p")
    request.state.lunch_break_hours = lunch_hours
