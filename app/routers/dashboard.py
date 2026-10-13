from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import datetime

from app.database import get_db
from app.dependencies import require_auth
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.document import EmployeeDocument
from app.models.payroll import Payslip
from app.models.department import Department
from app.utils.timezone import get_ist_today
from app.templates_config import templates
from app.routers.leaves import auto_lapse_pending_requests

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    auto_lapse_pending_requests(db)
    today = get_ist_today()
    attendance_today = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today
    ).first()
    
    stats = {}
    recent_attendances = []
    if current_user.role in ['super_admin', 'admin', 'hr', 'hr_admin']:
        hr_zone_restricted = (
            current_user.role in ['hr', 'hr_admin']
            and getattr(current_user, "hr_zone_scope", "all_zones") == "zone_only"
            and current_user.zone_id is not None
        )
        emp_q = db.query(Employee).filter(Employee.is_active == True, Employee.role != 'super_admin')
        if hr_zone_restricted:
            emp_q = emp_q.filter(Employee.zone_id == current_user.zone_id)
        stats['total_employees'] = emp_q.count()

        att_q = (
            db.query(Attendance)
            .join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.role != 'super_admin',
                Attendance.date == today,
                Attendance.check_in.isnot(None)
            )
        )
        if hr_zone_restricted:
            att_q = att_q.filter(Employee.zone_id == current_user.zone_id)
        stats['present_today'] = att_q.count()

        doc_q = db.query(EmployeeDocument).filter(EmployeeDocument.status == 'pending')
        if hr_zone_restricted:
            doc_q = doc_q.join(Employee, EmployeeDocument.employee_id == Employee.id).filter(Employee.zone_id == current_user.zone_id)
        stats['pending_docs'] = doc_q.count()

        stats['draft_payslips'] = db.query(Payslip).filter(
            Payslip.status == 'draft'
        ).count()

        rec_att_q = (
            db.query(Attendance)
            .join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.role != 'super_admin',
                Attendance.date == today
            )
        )
        if hr_zone_restricted:
            rec_att_q = rec_att_q.filter(Employee.zone_id == current_user.zone_id)
        recent_attendances = (
            rec_att_q.order_by(Attendance.check_in.desc())
            .limit(5)
            .all()
        )
    else:
        # For regular employee, get personal monthly attendance count & latest payslip
        stats['my_present_days'] = db.query(Attendance).filter(
            Attendance.employee_id == current_user.id,
            Attendance.date >= today.replace(day=1),
            Attendance.check_in.isnot(None)
        ).count()
        stats['my_pending_docs'] = db.query(EmployeeDocument).filter(
            EmployeeDocument.employee_id == current_user.id,
            EmployeeDocument.status == 'pending'
        ).count()
        stats['latest_payslip'] = db.query(Payslip).filter(
            Payslip.employee_id == current_user.id
        ).order_by(Payslip.year.desc(), Payslip.month.desc()).first()

    return templates.TemplateResponse(
        request, 
        "dashboard/dashboard.html", 
        {
            "user": current_user, 
            "attendance_today": attendance_today,
            "stats": stats,
            "recent_attendances": recent_attendances,
            "today": today
        }
    )
