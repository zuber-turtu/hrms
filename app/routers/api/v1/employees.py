from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from io import BytesIO
import openpyxl
import datetime

from app.database import get_db
from app.models.employee import (
    Employee,
    EmployeeProfile,
    EmployeeBankAccount,
    EmployeeEmergencyContact,
    SalaryStructure,
)
from app.models.department import Department, Designation
from app.models.audit import AuditLog
from app.dependencies import (
    require_auth,
    RoleChecker,
    get_password_hash,
)
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeOut,
    AdminPasswordReset,
)
from app.routers.employees import resolve_dept_and_desig

router = APIRouter(prefix="/employees", tags=["Employees"])

allow_hr_admin = RoleChecker(["admin", "hr_admin"])
allow_managers = RoleChecker(["admin", "hr_admin", "manager"])


def _format_employee_out(emp: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=emp.id,
        name=emp.name,
        email=emp.email,
        role=emp.role,
        department_id=emp.department_id,
        designation_id=emp.designation_id,
        department_name=emp.department.name if emp.department else None,
        designation_title=emp.designation.title if emp.designation else None,
        joining_date=emp.joining_date,
        is_active=emp.is_active,
        phone_number=emp.phone_number,
        gender=emp.gender,
        home_address=emp.home_address,
        city=emp.city,
        state=emp.state,
        country=emp.country,
        qualification=emp.qualification,
        experience=emp.experience,
        aadhar_number=emp.aadhar_number,
        pan_number=emp.pan_number,
        bank_name=emp.bank_name,
        account_number=emp.account_number,
        ifsc_code=emp.ifsc_code,
        emergency_contact_name=emp.emergency_contact_name,
        emergency_contact=emp.emergency_contact,
        emergency_contact_relation=emp.emergency_contact_relation,
        base_salary=emp.base_salary,
        hra=emp.hra,
        custom_allowances=emp.custom_allowances,
        pf_deduction=emp.pf_deduction,
        tax_deduction=emp.tax_deduction,
        profile=emp.profile,
        salary_structure=emp.salary_structure,
        bank_account=emp.bank_account,
    )


@router.get("", response_model=List[EmployeeOut])
@router.get("/", response_model=List[EmployeeOut])
async def api_list_employees(
    q: Optional[str] = None,
    role: Optional[str] = None,
    department_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_managers),
):
    """
    List all employees with optional search, role, and department filters.
    Managers are automatically scoped to their own department.
    """
    query = db.query(Employee)

    # Manager Department Scoping
    if current_user.role == "manager":
        query = query.filter(
            Employee.department_id == current_user.department_id,
            Employee.role.notin_(["admin", "hr_admin"]),
        )
    elif department_id:
        query = query.filter(Employee.department_id == department_id)

    if q and q.strip():
        search_term = f"%{q.strip()}%"
        query = (
            query.outerjoin(Department, Employee.department_id == Department.id)
            .outerjoin(Designation, Employee.designation_id == Designation.id)
            .filter(
                (Employee.name.ilike(search_term))
                | (Employee.email.ilike(search_term))
                | (Department.name.ilike(search_term))
                | (Designation.title.ilike(search_term))
            )
        )

    if role and role.strip() and role.strip() != "all":
        query = query.filter(Employee.role == role.strip())

    employees = query.order_by(Employee.id.asc()).offset(offset).limit(limit).all()
    return [_format_employee_out(emp) for emp in employees]


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def api_create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Onboard a new employee with optional profile details and salary structure (Admin / HR Admin only).
    """
    clean_email = payload.email.strip().lower()
    existing = db.query(Employee).filter(Employee.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An employee with this email address already exists.",
        )

    dept_id, desig_id = resolve_dept_and_desig(
        db,
        payload.department_id,
        payload.designation_id,
        payload.department_name,
        payload.designation_title,
    )

    new_employee = Employee(
        name=payload.name.strip(),
        email=clean_email,
        hashed_password=get_password_hash(payload.password),
        role=payload.role or "employee",
        department_id=dept_id,
        designation_id=desig_id,
        joining_date=payload.joining_date,
    )
    db.add(new_employee)
    db.flush()

    # Profile Creation (support both nested and flat fields)
    profile_data = payload.profile.dict(exclude_unset=True) if payload.profile else {}
    phone = payload.phone_number or payload.phone
    if phone:
        profile_data["phone_number"] = phone
    if payload.gender:
        profile_data["gender"] = payload.gender
    if payload.home_address:
        profile_data["home_address"] = payload.home_address
    if payload.city:
        profile_data["city"] = payload.city
    if payload.state:
        profile_data["state"] = payload.state
    if payload.country:
        profile_data["country"] = payload.country
    if payload.qualification:
        profile_data["qualification"] = payload.qualification
    if payload.experience:
        profile_data["experience"] = payload.experience
    if payload.aadhar_number:
        profile_data["aadhar_number"] = payload.aadhar_number
    if payload.pan_number:
        profile_data["pan_number"] = payload.pan_number

    profile = EmployeeProfile(employee_id=new_employee.id, **profile_data)
    db.add(profile)

    # Bank Account
    if payload.bank_name or payload.account_number or payload.ifsc_code:
        bank = EmployeeBankAccount(
            employee_id=new_employee.id,
            bank_name=payload.bank_name,
            account_number=payload.account_number,
            ifsc_code=payload.ifsc_code,
        )
        db.add(bank)

    # Emergency Contact
    emer_phone = payload.emergency_contact_phone
    if payload.emergency_contact_name or emer_phone:
        contact = EmployeeEmergencyContact(
            employee_id=new_employee.id,
            contact_name=payload.emergency_contact_name,
            phone_number=emer_phone,
            relationship=payload.emergency_contact_relation,
            is_primary=True,
        )
        db.add(contact)

    # Salary Structure Creation
    salary_data = payload.salary.dict(exclude_unset=True) if payload.salary else {}
    if payload.base_salary is not None:
        salary_data["base_salary"] = payload.base_salary
    if payload.hra is not None:
        salary_data["hra"] = payload.hra
    if payload.custom_allowances is not None:
        salary_data["custom_allowances"] = payload.custom_allowances
    if payload.pf_deduction is not None:
        salary_data["pf_deduction"] = payload.pf_deduction
    if payload.tax_deduction is not None:
        salary_data["tax_deduction"] = payload.tax_deduction

    salary = SalaryStructure(employee_id=new_employee.id, **salary_data)
    db.add(salary)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_EMPLOYEE",
        entity="Employee",
        entity_id=new_employee.id,
        new_value=f"{new_employee.name} ({new_employee.email}) - {new_employee.role}",
    )
    db.add(audit)
    db.commit()
    db.refresh(new_employee)

    return _format_employee_out(new_employee)


@router.get("/{emp_id}", response_model=EmployeeOut)
async def api_get_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Get detailed employee information including profile and salary structure.
    """
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    # Authorization / Scoping
    if current_user.id != emp_id and current_user.role not in ["admin", "hr_admin"]:
        if current_user.role == "manager":
            if (
                not current_user.department_id
                or employee.department_id != current_user.department_id
                or employee.role in ["admin", "hr_admin"]
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

    return _format_employee_out(employee)


@router.put("/{emp_id}", response_model=EmployeeOut)
async def api_update_employee(
    emp_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Update employee record. Basic contact details can be updated by self or admins.
    Roles, departments, joining date, and salaries can only be updated by Admins / HR Admins.
    """
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    is_admin = current_user.role in ["admin", "hr_admin"]
    if current_user.id != emp_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted"
        )

    if payload.email:
        clean_email = payload.email.strip().lower()
        if clean_email != employee.email:
            existing = (
                db.query(Employee)
                .filter(Employee.email == clean_email, Employee.id != emp_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered to another account.",
                )
            employee.email = clean_email

    if payload.name:
        employee.name = payload.name.strip()

    # Admin restricted updates
    if is_admin:
        if payload.role:
            if payload.role != employee.role:
                audit = AuditLog(
                    actor_id=current_user.id,
                    actor_email=current_user.email,
                    action="ROLE_CHANGE",
                    entity="Employee",
                    entity_id=emp_id,
                    old_value=employee.role,
                    new_value=payload.role,
                )
                db.add(audit)
                employee.role = payload.role

        if payload.joining_date is not None:
            employee.joining_date = payload.joining_date

        if payload.is_active is not None:
            employee.is_active = payload.is_active

        dept_id, desig_id = resolve_dept_and_desig(
            db,
            payload.department_id,
            payload.designation_id,
            payload.department_name,
            payload.designation_title,
        )
        if payload.department_id or payload.department_name:
            employee.department_id = dept_id
        if payload.designation_id or payload.designation_title:
            employee.designation_id = desig_id

        # Salary Structure Update
        if not employee.salary_structure:
            employee.salary_structure = SalaryStructure(employee_id=employee.id)
            db.add(employee.salary_structure)

        if payload.salary:
            salary_data = payload.salary.dict(exclude_unset=True)
            for k, v in salary_data.items():
                setattr(employee.salary_structure, k, v)
        if payload.base_salary is not None:
            employee.salary_structure.base_salary = payload.base_salary
        if payload.hra is not None:
            employee.salary_structure.hra = payload.hra
        if payload.custom_allowances is not None:
            employee.salary_structure.custom_allowances = payload.custom_allowances
        if payload.pf_deduction is not None:
            employee.salary_structure.pf_deduction = payload.pf_deduction
        if payload.tax_deduction is not None:
            employee.salary_structure.tax_deduction = payload.tax_deduction

    # Profile Update
    if not employee.profile:
        employee.profile = EmployeeProfile(employee_id=employee.id)
        db.add(employee.profile)

    if payload.profile:
        profile_data = payload.profile.dict(exclude_unset=True)
        for k, v in profile_data.items():
            setattr(employee.profile, k, v)

    phone = payload.phone_number or payload.phone
    if phone is not None:
        employee.profile.phone_number = phone
    if payload.gender is not None:
        employee.profile.gender = payload.gender
    if payload.home_address is not None:
        employee.profile.home_address = payload.home_address
    if payload.city is not None:
        employee.profile.city = payload.city
    if payload.state is not None:
        employee.profile.state = payload.state
    if payload.country is not None:
        employee.profile.country = payload.country
    if payload.qualification is not None:
        employee.profile.qualification = payload.qualification
    if payload.experience is not None:
        employee.profile.experience = payload.experience
    if payload.aadhar_number is not None:
        employee.profile.aadhar_number = payload.aadhar_number
    if payload.pan_number is not None:
        employee.profile.pan_number = payload.pan_number

    # Bank Account Update
    if payload.bank_name or payload.account_number or payload.ifsc_code:
        if not employee.bank_account:
            employee.bank_account = EmployeeBankAccount(employee_id=employee.id)
            db.add(employee.bank_account)
        if payload.bank_name is not None:
            employee.bank_account.bank_name = payload.bank_name
        if payload.account_number is not None:
            employee.bank_account.account_number = payload.account_number
        if payload.ifsc_code is not None:
            employee.bank_account.ifsc_code = payload.ifsc_code

    db.commit()
    db.refresh(employee)
    return _format_employee_out(employee)


@router.post("/{emp_id}/reset-password")
async def api_admin_reset_password(
    emp_id: int,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    Administrative password reset. Only super-admins can reset credentials for admin accounts.
    """
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )

    # Privilege Escalation Protection
    if employee.role == "admin" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted: Only Admins can reset credentials for an Administrator account.",
        )

    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters.",
        )

    employee.hashed_password = get_password_hash(payload.new_password)
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="ADMIN_PASSWORD_RESET",
        entity="Employee",
        entity_id=emp_id,
        old_value="[PROTECTED]",
        new_value="[PROTECTED]",
    )
    db.add(audit)
    db.commit()

    return {"message": f"Password for {employee.name} reset successfully."}
