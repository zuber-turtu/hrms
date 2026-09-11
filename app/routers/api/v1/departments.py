from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department, Designation
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.schemas.department import (
    DepartmentCreate,
    DepartmentOut,
    DesignationCreate,
    DesignationOut,
)

router = APIRouter(prefix="/departments", tags=["Departments & Designations"])
allow_hr_admin = RoleChecker(["admin", "hr_admin"])


@router.get("", response_model=List[DepartmentOut])
@router.get("/", response_model=List[DepartmentOut])
async def api_list_departments(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Get all departments with their associated designations.
    """
    departments = db.query(Department).order_by(Department.name.asc()).all()
    return departments


@router.post("", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def api_create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Create a new department (Admin / HR Admin).
    """
    name_clean = payload.name.strip()
    code_clean = payload.code.strip().upper() if payload.code else None

    existing_name = db.query(Department).filter(Department.name.ilike(name_clean)).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A department with this name already exists.",
        )

    if code_clean:
        existing_code = db.query(Department).filter(Department.code == code_clean).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A department with code '{code_clean}' already exists.",
            )

    dept = Department(name=name_clean, code=code_clean)
    db.add(dept)
    db.commit()
    db.refresh(dept)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_DEPARTMENT",
        entity="Department",
        entity_id=dept.id,
        new_value=f"{dept.name} ({dept.code})",
    )
    db.add(audit)
    db.commit()

    return dept


@router.put("/{dept_id}", response_model=DepartmentOut)
async def api_update_department(
    dept_id: int,
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Update department name or code.
    """
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )

    name_clean = payload.name.strip()
    code_clean = payload.code.strip().upper() if payload.code else None

    existing_name = (
        db.query(Department)
        .filter(Department.name.ilike(name_clean), Department.id != dept_id)
        .first()
    )
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A department with this name already exists.",
        )

    if code_clean:
        existing_code = (
            db.query(Department)
            .filter(Department.code == code_clean, Department.id != dept_id)
            .first()
        )
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A department with code '{code_clean}' already exists.",
            )

    old_val = f"{dept.name} ({dept.code})"
    dept.name = name_clean
    dept.code = code_clean

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="UPDATE_DEPARTMENT",
        entity="Department",
        entity_id=dept.id,
        old_value=old_val,
        new_value=f"{dept.name} ({dept.code})",
    )
    db.add(audit)
    db.commit()
    db.refresh(dept)

    return dept


@router.delete("/{dept_id}")
async def api_delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Delete a department and reassign associated employees to unassigned.
    """
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )

    dept_name = dept.name
    # Unlink employees
    db.query(Employee).filter(Employee.department_id == dept_id).update(
        {"department_id": None, "designation_id": None}
    )
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

    return {"message": f"Department '{dept_name}' deleted successfully."}


@router.post("/{dept_id}/designations", response_model=DesignationOut, status_code=status.HTTP_201_CREATED)
async def api_create_designation(
    dept_id: int,
    payload: DesignationCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Add a designation title under a department.
    """
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )

    title_clean = payload.title.strip()
    desig = Designation(title=title_clean, department_id=dept_id)
    db.add(desig)
    db.commit()
    db.refresh(desig)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_DESIGNATION",
        entity="Designation",
        entity_id=desig.id,
        new_value=f"{desig.title} (Dept: {dept.name})",
    )
    db.add(audit)
    db.commit()

    return desig


@router.delete("/designations/{desig_id}")
async def api_delete_designation(
    desig_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Delete a designation title.
    """
    desig = db.query(Designation).filter(Designation.id == desig_id).first()
    if not desig:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Designation not found"
        )

    title = desig.title
    db.query(Employee).filter(Employee.designation_id == desig_id).update(
        {"designation_id": None}
    )
    db.delete(desig)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="DELETE_DESIGNATION",
        entity="Designation",
        entity_id=desig_id,
        old_value=title,
        new_value="DELETED",
    )
    db.add(audit)
    db.commit()

    return {"message": f"Designation '{title}' deleted successfully."}
