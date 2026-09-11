from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department, Designation
from app.dependencies import RoleChecker
from app.models.audit import AuditLog

router = APIRouter(prefix="/departments")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["admin", "hr_admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_departments(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    departments = db.query(Department).all()
    designations = db.query(Designation).all()
    
    return templates.TemplateResponse(
        request=request,
        name="departments/manage.html",
        context={
            "user": current_user,
            "departments": departments,
            "designations": designations,
        },
    )


@router.post("/create")
async def create_department(
    request: Request,
    name: str = Form(...),
    code: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    clean_name = name.strip()
    existing = db.query(Department).filter(Department.name == clean_name).first()
    if existing:
        return RedirectResponse(url="/departments?error=Department+already+exists", status_code=302)

    dept = Department(
        name=clean_name,
        code=code.strip().upper() if code and code.strip() else clean_name[:4].upper(),
        description=description.strip() if description else None,
    )
    db.add(dept)
    db.commit()

    # Record Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_DEPARTMENT",
        entity="Department",
        entity_id=dept.id,
        old_value="None",
        new_value=dept.name,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/departments?success=Department+created+successfully", status_code=302)


@router.post("/{dept_id}/edit")
async def edit_department(
    dept_id: int,
    request: Request,
    name: str = Form(...),
    code: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    old_name = dept.name
    dept.name = name.strip()
    dept.code = code.strip().upper() if code and code.strip() else dept.name[:4].upper()
    dept.description = description.strip() if description else None

    # Record Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="EDIT_DEPARTMENT",
        entity="Department",
        entity_id=dept.id,
        old_value=old_name,
        new_value=dept.name,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/departments?success=Department+updated+successfully", status_code=302)


@router.post("/{dept_id}/delete")
async def delete_department(
    dept_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Safety check: Cannot delete if active employees belong to this department
    assigned_employees = db.query(Employee).filter(Employee.department_id == dept_id).count()
    if assigned_employees > 0:
        return RedirectResponse(
            url=f"/departments?error=Cannot+delete+department+with+{assigned_employees}+assigned+employees",
            status_code=302,
        )

    dept_name = dept.name
    db.delete(dept)
    
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="DELETE_DEPARTMENT",
        entity="Department",
        entity_id=dept_id,
        old_value=dept_name,
        new_value="DELETED",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/departments?success=Department+deleted+successfully", status_code=302)


# ================= DESIGNATIONS =================

@router.post("/designations/create")
async def create_designation(
    request: Request,
    title: str = Form(...),
    department_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    clean_title = title.strip()
    desig = Designation(
        title=clean_title,
        department_id=department_id if department_id and department_id > 0 else None,
        description=description.strip() if description else None,
    )
    db.add(desig)
    db.commit()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_DESIGNATION",
        entity="Designation",
        entity_id=desig.id,
        old_value="None",
        new_value=desig.title,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/departments?success=Designation+created+successfully", status_code=302)


@router.post("/designations/{desig_id}/edit")
async def edit_designation(
    desig_id: int,
    request: Request,
    title: str = Form(...),
    department_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    desig = db.query(Designation).filter(Designation.id == desig_id).first()
    if not desig:
        raise HTTPException(status_code=404, detail="Designation not found")

    old_title = desig.title
    desig.title = title.strip()
    desig.department_id = department_id if department_id and department_id > 0 else None
    desig.description = description.strip() if description else None

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="EDIT_DESIGNATION",
        entity="Designation",
        entity_id=desig.id,
        old_value=old_title,
        new_value=desig.title,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/departments?success=Designation+updated+successfully", status_code=302)


@router.post("/designations/{desig_id}/delete")
async def delete_designation(
    desig_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    desig = db.query(Designation).filter(Designation.id == desig_id).first()
    if not desig:
        raise HTTPException(status_code=404, detail="Designation not found")

    assigned_employees = db.query(Employee).filter(Employee.designation_id == desig_id).count()
    if assigned_employees > 0:
        return RedirectResponse(
            url=f"/departments?error=Cannot+delete+designation+with+{assigned_employees}+assigned+employees",
            status_code=302,
        )

    desig_title = desig.title
    db.delete(desig)
    
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="DELETE_DESIGNATION",
        entity="Designation",
        entity_id=desig_id,
        old_value=desig_title,
        new_value="DELETED",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/departments?success=Designation+deleted+successfully", status_code=302)


# ================= API ENDPOINT FOR DYNAMIC DROPDOWNS =================

@router.get("/api/list")
async def api_get_departments_and_designations(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    departments = db.query(Department).all()
    result = []
    for d in departments:
        result.append({
            "id": d.id,
            "name": d.name,
            "code": d.code,
            "designations": [{"id": des.id, "title": des.title} for des in d.designations],
        })
    return JSONResponse(content={"departments": result})


@router.get("/designations/options", response_class=HTMLResponse)
@router.get("/{dept_id}/designations/options", response_class=HTMLResponse)
async def get_designations_options(
    request: Request,
    dept_id: Optional[str] = None,
    department_id: Optional[str] = None,
    selected_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(RoleChecker(["admin", "hr_admin", "manager", "employee", "intern"])),
):
    target_id = dept_id or department_id or request.query_params.get("department_id") or request.query_params.get("department")
    if not target_id or target_id in ("all", "", "0"):
        return HTMLResponse('<option value="">-- Select Designation --</option>')
    try:
        d_id = int(target_id)
    except ValueError:
        return HTMLResponse('<option value="">-- Select Designation --</option>')
        
    designations = (
        db.query(Designation)
        .filter(Designation.department_id == d_id)
        .order_by(Designation.title.asc())
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="departments/partials/_designation_options.html",
        context={"designations": designations, "selected_id": selected_id}
    )
