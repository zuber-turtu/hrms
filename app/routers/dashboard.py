from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import datetime

from app.database import get_db
from app.dependencies import require_auth
from app.models.employee import Employee
from app.models.attendance import Attendance

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
    
    return templates.TemplateResponse(
        request, 
        "dashboard/dashboard.html", 
        {"user": current_user, "attendance_today": attendance_today}
    )

