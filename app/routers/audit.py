from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.dependencies import RoleChecker

router = APIRouter(prefix="/audit")
templates = Jinja2Templates(directory="app/templates")

allow_admin = RoleChecker(["admin"])


@router.get("/", response_class=HTMLResponse)
async def view_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin),
):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    return templates.TemplateResponse(
        request, "audit/logs.html", {"user": current_user, "logs": logs}
    )
