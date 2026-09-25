from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    today = get_ist_today()
    attendance_today = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        Attendance.date == today
    ).first()
    
    stats = {}
    recent_attendances = []
    if current_user.role in ['admin', 'hr_admin']:
        stats['total_employees'] = db.query(Employee).filter(Employee.is_active == True, Employee.role != 'admin').count()
        stats['present_today'] = (
            db.query(Attendance)
            .join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.role != 'admin',
                Attendance.date == today,
                Attendance.check_in.isnot(None)
            )
            .count()
        )
        stats['pending_docs'] = db.query(EmployeeDocument).filter(
            EmployeeDocument.status == 'pending'
        ).count()
        stats['draft_payslips'] = db.query(Payslip).filter(
            Payslip.status == 'draft'
        ).count()
        recent_attendances = (
            db.query(Attendance)
            .join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Employee.role != 'admin',
                Attendance.date == today
            )
            .order_by(Attendance.check_in.desc())
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
