from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department, Designation
from app.models.company import Company
from app.dependencies import RoleChecker
from app.models.audit import AuditLog
from app.templates_config import templates
from app.utils.flash import flash_redirect
from app.services.excel_exporter import export_departments_excel

router = APIRouter(prefix="/departments")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])


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
        return flash_redirect(url="/departments", message="Department already exists", category="error")

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

    return flash_redirect(url="/departments", message="Department created successfully", category="success")


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

    return flash_redirect(url="/departments", message="Department updated successfully", category="success")


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
        return flash_redirect(
            url="/departments",
            message=f"Cannot delete department with {assigned_employees} assigned employees",
            category="error",
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

    return flash_redirect(url="/departments", message="Department deleted successfully", category="success")


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

    return flash_redirect(url="/departments", message="Designation created successfully", category="success")


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

    return flash_redirect(url="/departments", message="Designation updated successfully", category="success")


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
        return flash_redirect(
            url="/departments",
            message=f"Cannot delete designation with {assigned_employees} assigned employees",
            category="error",
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

    return flash_redirect(url="/departments", message="Designation deleted successfully", category="success")


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
    current_user: Employee = Depends(RoleChecker(["super_admin", "admin", "hr", "hr_admin", "manager", "employee", "intern"])),
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


# ================= EMPLOYEE ROSTER ENDPOINTS =================

@router.get("/designations/{desig_id}/employees", response_class=HTMLResponse)
async def get_designation_employees(
    request: Request,
    desig_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    designation = db.query(Designation).filter(Designation.id == desig_id).first()
    if not designation:
        raise HTTPException(status_code=404, detail="Designation not found")

    employees = (
        db.query(Employee)
        .filter(Employee.designation_id == desig_id)
        .order_by(Employee.name.asc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="departments/partials/_employees_modal.html",
        context={
            "user": current_user,
            "target_type": "designation",
            "target_object": designation,
            "employees": employees,
        },
    )


@router.get("/{dept_id}/employees", response_class=HTMLResponse)
async def get_department_employees(
    request: Request,
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    department = db.query(Department).filter(Department.id == dept_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    employees = (
        db.query(Employee)
        .filter(Employee.department_id == dept_id)
        .order_by(Employee.name.asc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="departments/partials/_employees_modal.html",
        context={
            "user": current_user,
            "target_type": "department",
            "target_object": department,
            "employees": employees,
        },
    )


@router.get("/export-excel")
async def export_departments_spreadsheet(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Exports corporate business units and headcount roster to Excel."""
    departments = db.query(Department).order_by(Department.name.asc()).all()
    company = db.query(Company).first()
    return export_departments_excel(departments, company)
