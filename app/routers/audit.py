from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company
from app.models.audit import AuditLog
from app.dependencies import RoleChecker
from app.templates_config import templates
from app.utils.pagination import paginate_query
from app.services.excel_exporter import export_audit_logs_excel

router = APIRouter(prefix="/audit")

allow_admin = RoleChecker(["super_admin", "admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def view_audit_logs(
    request: Request,
    page: Optional[int] = 1,
    page_size: Optional[int] = 25,
    q: Optional[str] = None,
    date: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin),
):
    query = db.query(AuditLog)

    # Search keyword filter
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                AuditLog.actor_email.ilike(term),
                AuditLog.action.ilike(term),
                AuditLog.entity.ilike(term),
                AuditLog.old_value.ilike(term),
                AuditLog.new_value.ilike(term),
            )
        )

    # Date filter (exact match on YYYY-MM-DD)
    if date and date.strip():
        query = query.filter(func.date(AuditLog.timestamp) == date.strip())

    # Action type filter
    if action and action.strip() and action.lower() != "all":
        query = query.filter(AuditLog.action.contains(action.strip().upper()))

    query = query.order_by(AuditLog.timestamp.desc())

    page_data = paginate_query(query, page=page, page_size=page_size)

    context = {
        "request": request,
        "user": current_user,
        "page_data": page_data,
        "q": q or "",
        "date": date or "",
        "action": action or "all",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "audit/partials/_logs_table.html", context)

    return templates.TemplateResponse(request, "audit/logs.html", context)


@router.get("/export-excel")
async def export_audit_logs_spreadsheet(
    q: Optional[str] = None,
    date: Optional[str] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin),
):
    """Exports security activity audit logs to Excel."""
    query = db.query(AuditLog)

    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                AuditLog.actor_email.ilike(term),
                AuditLog.action.ilike(term),
                AuditLog.entity.ilike(term),
                AuditLog.old_value.ilike(term),
                AuditLog.new_value.ilike(term),
            )
        )

    if date and date.strip():
        query = query.filter(func.date(AuditLog.timestamp) == date.strip())

    if action and action.strip() and action.lower() != "all":
        query = query.filter(AuditLog.action.contains(action.strip().upper()))

    logs = query.order_by(AuditLog.timestamp.desc()).all()
    company = db.query(Company).first()
    return export_audit_logs_excel(logs, company)

