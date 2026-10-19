import json
from urllib.parse import quote_plus
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import cast, String
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from app.database import get_db
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.company import Company
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.config import settings
from app.utils.geofence import validate_punch_geofence, get_active_wfh_request
from app.services.excel_exporter import export_attendance_excel, export_attendance_monthly_matrix_excel

from app.utils.timezone import get_ist_today, get_ist_now
from app.utils.security import get_safe_redirect
from app.utils.attendance import update_attendance_request_state
from app.utils.permissions import assert_can_manage_employee, can_manage_employee

from app.templates_config import templates

router = APIRouter(prefix="/attendance")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin", "manager"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def attendance_log(
    request: Request,
    page: Optional[int] = 1,
    page_size: Optional[int] = 25,
    q: Optional[str] = None,
    date: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    from collections import defaultdict
    import math
    from app.utils.pagination import PageResult, generate_page_numbers
    
    query = db.query(Attendance)

    if current_user.role in ["employee", "intern"]:
        query = query.filter(Attendance.employee_id == current_user.id)
    elif current_user.role == "manager":
        # Scoped to own department subordinates
        query = (
            query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.department_id == current_user.department_id,
                Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
            )
        )
    elif current_user.role in ["hr", "hr_admin"] and getattr(current_user, "hr_zone_scope", "all_zones") == "zone_only" and current_user.zone_id:
        query = (
            query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(Employee.role != "super_admin", Employee.zone_id == current_user.zone_id)
        )
    else:
        query = (
            query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(Employee.role != "super_admin")
        )

    today = get_ist_today()
    now_ist = get_ist_now()

    # Filter by date at database level, or default to recent window (last 45 days) to prevent unbounded full-table scans
    if date and date.strip():
        query = query.filter(Attendance.date == date.strip())
    else:
        window_start = today - datetime.timedelta(days=45)
        query = query.filter(Attendance.date >= window_start)

    # Search keyword filtering directly in SQL
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        if current_user.role in ["employee", "intern"]:
            query = query.join(Employee, Attendance.employee_id == Employee.id)
        query = query.filter(
            (Employee.name.ilike(search_term))
            | (Employee.email.ilike(search_term))
            | (cast(Attendance.date, String).ilike(search_term))
        )

    # Status filter directly in SQL
    if status and status.strip() and status.strip() != "all":
        st = status.strip().lower()
        if st == "missed":
            query = query.filter(Attendance.check_out.is_(None), Attendance.date < today)
        elif st == "overridden":
            query = query.filter(Attendance.is_overridden == True)
        elif st == "normal":
            query = query.filter(
                Attendance.is_overridden == False,
                or_(Attendance.check_out.isnot(None), Attendance.date >= today)
            )

    # Stage 1: Paginate distinct (date, employee_id) pairs directly in SQL
    distinct_q = query.with_entities(Attendance.date, Attendance.employee_id).distinct()
    total_records = distinct_q.count()
    size_int = max(1, min(int(page_size or 25), 100))
    total_pages = max(1, math.ceil(total_records / size_int))
    page_int = min(max(1, int(page or 1)), total_pages)
    offset = (page_int - 1) * size_int

    page_pairs = (
        distinct_q.order_by(Attendance.date.desc(), Attendance.employee_id.asc())
        .offset(offset)
        .limit(size_int)
        .all()
    )

    # Stage 2: Fetch only the punch rows matching those target pairs
    logs_data = []
    if page_pairs:
        from sqlalchemy.orm import joinedload
        from sqlalchemy import and_, or_
        pair_filters = [and_(Attendance.date == d, Attendance.employee_id == eid) for d, eid in page_pairs]
        target_logs = (
            db.query(Attendance)
            .options(
                joinedload(Attendance.employee).joinedload(Employee.profile),
                joinedload(Attendance.employee).joinedload(Employee.zone)
            )
            .filter(or_(*pair_filters))
            .order_by(Attendance.date.desc(), Attendance.check_in.desc(), Attendance.id.desc())
            .all()
        )
        grouped = defaultdict(list)
        for log in target_logs:
            grouped[(log.date, log.employee_id)].append(log)

        for (log_date, emp_id) in page_pairs:
            group_logs = grouped.get((log_date, emp_id), [])
            if not group_logs:
                continue
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
                if not start and not log.check_out:
                    sessions.append("No Punch")
                    continue

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
                
                if start and end:
                    diff = (end - start).total_seconds()
                    total_seconds += max(0, diff)
                
                in_str = log.check_in.strftime('%I:%M %p') if log.check_in else "--"
                sessions.append(f"{in_str} - {out_str}")
                
            hrs = int(total_seconds // 3600)
            mins = int((total_seconds % 3600) // 60)
            secs = int(total_seconds % 60)
            total_active_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
            
            latest_log = group_logs[0]
            latest_dist = latest_log.check_in_distance_m if latest_log.check_in_distance_m is not None else latest_log.check_out_distance_m
            latest_in_range = latest_log.check_in_in_range if latest_log.check_in_in_range is not None else latest_log.check_out_in_range
            is_exempt = bool(employee and employee.profile and employee.profile.is_geofence_exempt)
            work_mode = latest_log.work_mode or ("wfh" if latest_log.wfh_request_id else "office")
            loc_name = latest_log.check_in_location_name or latest_log.check_out_location_name or ("Office" if latest_in_range else "Outside Perimeter")

            item = {
                "id": latest_log.id,  # primary ID for override actions (latest punch session)
                "date": log_date,
                "employee": employee,
                "sessions": ", ".join(sessions),
                "total_active": f"{total_active_str} (Missed)" if is_missed else total_active_str,
                "is_overridden": is_overridden,
                "override_reason": override_reason,
                "is_missed": is_missed,
                "check_in": latest_log.check_in,
                "check_out": latest_log.check_out,
                "distance_m": latest_dist,
                "in_range": latest_in_range,
                "is_exempt": is_exempt,
                "work_mode": work_mode,
                "location_name": loc_name,
            }
            logs_data.append(item)

    start_record = (offset + 1) if total_records > 0 else 0
    end_record = min(offset + size_int, total_records)
    page_data = PageResult(
        items=logs_data,
        total_records=total_records,
        current_page=page_int,
        total_pages=total_pages,
        page_size=size_int,
        start_record=start_record,
        end_record=end_record,
        has_prev=page_int > 1,
        has_next=page_int < total_pages,
        prev_page=max(1, page_int - 1),
        next_page=min(total_pages, page_int + 1),
        page_numbers=generate_page_numbers(page_int, total_pages),
    )

    context_payload = {
        "request": request,
        "user": current_user,
        "page_data": page_data,
        "logs": page_data.items,
        "total_count": len(logs_data),
        "selected_date": date or "",
        "selected_status": status or "all",
        "q": q or ""
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="attendance/partials/_log_table.html",
            context=context_payload
        )

    return templates.TemplateResponse(
        request=request, name="attendance/log.html", context=context_payload
    )



@router.post("/check-in")
async def check_in(
    request: Request,
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    punch_reason: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role == "super_admin":
        if request.headers.get("HX-Request"):
            return HTMLResponse("")
        safe_target = get_safe_redirect(request, default="/dashboard")
        return RedirectResponse(url=safe_target, status_code=302)

    # 1. Validate Geofence
    geo_res = validate_punch_geofence(db, current_user, lat, lon)

    if not geo_res.is_allowed:
        if request.headers.get("HX-Request"):
            error_data = json.dumps({"message": geo_res.message or "Check-in outside office perimeter blocked.", "type": "error"})
            headers = {"HX-Trigger": f'{{"showErrorToast": {error_data}}}'}
            update_attendance_request_state(db, current_user, request)
            return templates.TemplateResponse(
                request,
                "attendance/partials/_topbar_widget.html",
                {"user": current_user, "punch_error": geo_res.message},
                headers=headers
            )

        safe_target = get_safe_redirect(request, default="/dashboard")
        separator = "&" if "?" in safe_target else "?"
        return RedirectResponse(
            url=f"{safe_target}{separator}error={quote_plus(geo_res.message or 'Punch outside allowed perimeter')}",
            status_code=302
        )

    today = get_ist_today()
    # Check if there is an active check-in (check_out is None)
    active_log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.check_out == None
    ).first()

    if not active_log:
        active_wfh = get_active_wfh_request(db, current_user.id, today)
        mode = "wfh" if active_wfh else ("office" if not geo_res.is_exempt else "remote")
        wfh_id = active_wfh.id if active_wfh else None
        now_time = get_ist_now()

        log = Attendance(
            employee_id=current_user.id,
            date=today,
            check_in=now_time,
            check_in_lat=lat,
            check_in_lon=lon,
            check_in_distance_m=geo_res.distance_meters,
            check_in_in_range=geo_res.in_range,
            check_in_location_name=geo_res.location_name,
            work_mode=mode,
            wfh_request_id=wfh_id,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        # Audit Log Entry
        loc_str = f" at {geo_res.location_name}" if geo_res.location_name else ""
        audit = AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="ATTENDANCE_CHECK_IN",
            entity="Attendance",
            entity_id=log.id,
            new_value=f"Check-In at {now_time.strftime('%I:%M %p')}{loc_str} ({mode.upper()})",
        )
        db.add(audit)
        db.commit()

    if request.headers.get("HX-Request"):
        update_attendance_request_state(db, current_user, request)
        headers = {
            "HX-Trigger": json.dumps({
                "refreshAttendanceLogs": True,
                "showSuccessToast": {"message": "Checked in successfully! Attendance ledger updated."}
            })
        }
        return templates.TemplateResponse(
            request,
            "attendance/partials/_topbar_widget.html",
            {"user": current_user},
            headers=headers
        )

    safe_target = get_safe_redirect(request, default="/dashboard")
    return RedirectResponse(url=safe_target, status_code=302)


@router.post("/check-out")
async def check_out(
    request: Request,
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    punch_reason: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role == "super_admin":
        if request.headers.get("HX-Request"):
            return HTMLResponse("")
        safe_target = get_safe_redirect(request, default="/dashboard")
        return RedirectResponse(url=safe_target, status_code=302)

    # 1. Validate Geofence
    geo_res = validate_punch_geofence(db, current_user, lat, lon)

    if not geo_res.is_allowed:
        if request.headers.get("HX-Request"):
            error_data = json.dumps({"message": geo_res.message or "Check-out outside office perimeter blocked.", "type": "error"})
            headers = {"HX-Trigger": f'{{"showErrorToast": {error_data}}}'}
            update_attendance_request_state(db, current_user, request)
            return templates.TemplateResponse(
                request,
                "attendance/partials/_topbar_widget.html",
                {"user": current_user, "punch_error": geo_res.message},
                headers=headers
            )

        safe_target = get_safe_redirect(request, default="/dashboard")
        separator = "&" if "?" in safe_target else "?"
        return RedirectResponse(
            url=f"{safe_target}{separator}error={quote_plus(geo_res.message or 'Punch outside allowed perimeter')}",
            status_code=302
        )

    today = get_ist_today()
    # Find the active check-in log to checkout
    log = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today,
        Attendance.check_out == None
    ).order_by(Attendance.check_in.desc()).first()

    if log:
        now_time = get_ist_now()
        log.check_out = now_time
        log.check_out_lat = lat
        log.check_out_lon = lon
        log.check_out_distance_m = geo_res.distance_meters
        log.check_out_in_range = geo_res.in_range
        log.check_out_location_name = geo_res.location_name
        if punch_reason and "lunch" in punch_reason.lower():
            log.override_reason = "Lunch Break"
        db.commit()

        # Audit Log Entry
        loc_str = f" at {geo_res.location_name}" if geo_res.location_name else ""
        diff_mins = int((now_time - log.check_in).total_seconds() // 60) if log.check_in else 0
        hrs = diff_mins // 60
        mins = diff_mins % 60
        audit = AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="ATTENDANCE_CHECK_OUT",
            entity="Attendance",
            entity_id=log.id,
            old_value=f"Check-In: {log.check_in.strftime('%I:%M %p') if log.check_in else 'N/A'}",
            new_value=f"Check-Out at {now_time.strftime('%I:%M %p')}{loc_str} (Duration: {hrs}h {mins}m)",
        )
        db.add(audit)
        db.commit()

    if request.headers.get("HX-Request"):
        update_attendance_request_state(db, current_user, request)
        headers = {
            "HX-Trigger": json.dumps({
                "refreshAttendanceLogs": True,
                "showSuccessToast": {"message": "Checked out successfully! Attendance ledger updated."}
            })
        }
        return templates.TemplateResponse(
            request,
            "attendance/partials/_topbar_widget.html",
            {"user": current_user},
            headers=headers
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

    if current_user.id == log.employee_id:
        raise HTTPException(
            status_code=403,
            detail="Operation not permitted: You cannot adjust your own attendance record."
        )

    # Hierarchical Privilege Enforcement: lower role cannot override attendance for equal or higher role
    assert_can_manage_employee(current_user, log.employee, "override attendance for")

    # Scope verification: Managers can only override records of subordinates in their own department
    if current_user.role == "manager":
        if (
            not current_user.department_id
            or log.employee.department_id != current_user.department_id
            or log.employee.role in ["super_admin", "admin", "hr", "hr_admin"]
        ):
            raise HTTPException(
                status_code=403,
                detail="Operation not permitted: Managers can only adjust attendance for subordinates in their department."
            )
    elif current_user.role in ["hr", "hr_admin"] and getattr(current_user, "hr_zone_scope", "all_zones") == "zone_only" and current_user.zone_id:
        if log.employee.zone_id != current_user.zone_id:
            raise HTTPException(
                status_code=403,
                detail="Operation not permitted: HR is restricted to their assigned operating zone."
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


# =========================================================================
# ATTENDANCE EXCEL EXPORT ENDPOINTS
# =========================================================================

@router.get("/export-excel")
async def export_attendance_logs_excel(
    q: Optional[str] = None,
    date: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Exports daily or filtered attendance punch records to Excel."""
    from collections import defaultdict
    query = db.query(Attendance)

    if current_user.role in ["employee", "intern"]:
        query = query.filter(Attendance.employee_id == current_user.id)
    elif current_user.role == "manager":
        query = (
            query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.department_id == current_user.department_id,
                Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
            )
        )
    elif current_user.role in ["hr", "hr_admin"] and getattr(current_user, "hr_zone_scope", "all_zones") == "zone_only" and current_user.zone_id:
        query = (
            query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(Employee.role != "super_admin", Employee.zone_id == current_user.zone_id)
        )
    else:
        query = (
            query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(Employee.role != "super_admin")
        )

    if date and date.strip():
        query = query.filter(Attendance.date == date.strip())

    raw_logs = query.order_by(Attendance.date.desc(), Attendance.check_in.desc(), Attendance.id.desc()).all()

    grouped = defaultdict(list)
    for log in raw_logs:
        grouped[(log.date, log.employee_id)].append(log)

    logs_data = []
    today = get_ist_today()
    now_ist = get_ist_now()

    for (log_date, emp_id), group_logs in grouped.items():
        employee = group_logs[0].employee
        total_seconds = 0
        is_overridden = False
        override_reason = ""

        for log in group_logs:
            if log.is_overridden:
                is_overridden = True
                override_reason = log.override_reason

            start = log.check_in
            if not start and not log.check_out:
                continue

            if log.check_out:
                end = log.check_out
            else:
                if log.date < today:
                    end = log.check_in
                else:
                    end = now_ist

            if start and end:
                diff = (end - start).total_seconds()
                total_seconds += max(0, diff)

        hrs = int(total_seconds // 3600)
        mins = int((total_seconds % 3600) // 60)
        hours_str = f"{hrs}h {mins}m"

        in_time_str = group_logs[0].check_in.strftime('%I:%M %p') if group_logs[0].check_in else "—"
        if not group_logs[0].check_in and not group_logs[-1].check_out:
            out_time_str = "—"
        else:
            out_time_str = group_logs[-1].check_out.strftime('%I:%M %p') if group_logs[-1].check_out else ("Active" if log_date == today else "Missed")

        work_mode = group_logs[0].work_mode or ("wfh" if group_logs[0].wfh_request_id else "office")
        if work_mode == "wfh":
            status_label = "WFH"
        elif hrs >= 8:
            status_label = "Present"
        elif hrs >= 4:
            status_label = "Half Day"
        else:
            status_label = "Short Shift"

        item = {
            "date": log_date,
            "employee": employee,
            "in_time_str": in_time_str,
            "out_time_str": out_time_str,
            "hours_str": hours_str,
            "status_label": status_label,
            "is_overridden": is_overridden,
            "override_reason": override_reason,
        }

        if q and q.strip():
            query_lower = q.strip().lower()
            emp_name = (employee.name or "").lower() if employee else ""
            date_str = str(log_date).lower()
            if query_lower not in emp_name and query_lower not in date_str:
                continue

        if status and status.strip() and status.lower() != "all":
            if status.lower() not in status_label.lower():
                continue

        logs_data.append(item)

    company = db.query(Company).first()
    return export_attendance_excel(logs_data, company, date_filter=date)


@router.get("/export-monthly-matrix")
async def export_monthly_matrix_endpoint(
    month: Optional[int] = None,
    year: Optional[int] = None,
    dept_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Exports full 31-day attendance timesheet matrix for a given month and year."""
    today = get_ist_today()
    sel_month = month if (month and 1 <= month <= 12) else today.month
    sel_year = year if (year and year > 2000) else today.year

    emp_query = db.query(Employee).filter(Employee.is_active == True, Employee.role != "super_admin")
    if current_user.role == "manager":
        emp_query = emp_query.filter(Employee.department_id == current_user.department_id)
    elif current_user.role in ["hr", "hr_admin"] and getattr(current_user, "hr_zone_scope", "all_zones") == "zone_only" and current_user.zone_id:
        emp_query = emp_query.filter(Employee.zone_id == current_user.zone_id)
    elif dept_id and dept_id > 0:
        emp_query = emp_query.filter(Employee.department_id == dept_id)

    employees = emp_query.order_by(Employee.name.asc()).all()

    import calendar
    _, days_in_month = calendar.monthrange(sel_year, sel_month)
    start_date = datetime.date(sel_year, sel_month, 1)
    end_date = datetime.date(sel_year, sel_month, days_in_month)

    attendance_records = db.query(Attendance).filter(
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).all()

    from collections import defaultdict
    grouped_matrix = defaultdict(lambda: {"days": {}})
    for rec in attendance_records:
        d_str = rec.date.strftime("%Y-%m-%d")
        work_mode = rec.work_mode or ("wfh" if rec.wfh_request_id else "office")
        if work_mode == "wfh":
            grouped_matrix[rec.employee_id]["days"][d_str] = "W"
        elif rec.check_in and rec.check_out:
            hrs = (rec.check_out - rec.check_in).total_seconds() / 3600.0
            grouped_matrix[rec.employee_id]["days"][d_str] = "P" if hrs >= 7.5 else ("HD" if hrs >= 3.5 else "P")
        else:
            grouped_matrix[rec.employee_id]["days"][d_str] = "P"

    company = db.query(Company).first()
    return export_attendance_monthly_matrix_excel(employees, grouped_matrix, sel_month, sel_year, company)
