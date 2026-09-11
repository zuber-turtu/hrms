from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.dependencies import RoleChecker
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/audit", tags=["Audit Logs"])
allow_admin_only = RoleChecker(["admin"])


@router.get("", response_model=List[AuditLogOut])
@router.get("/", response_model=List[AuditLogOut])
@router.get("/logs", response_model=List[AuditLogOut])
async def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action name"),
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    actor_id: Optional[int] = Query(None, description="Filter by actor ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action)
    if entity:
        query = query.filter(AuditLog.entity == entity)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)

    logs = (
        query.order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return logs
