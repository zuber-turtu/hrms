from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from io import BytesIO
import openpyxl
from typing import Optional

from app.database import get_db
from app.models.employee import (
    Employee,
    EmployeeProfile,
    EmployeeBankAccount,
    EmployeeEmergencyContact,
    SalaryStructure,
)
from app.models.department import Department, Designation
from app.dependencies import require_auth, RoleChecker, get_password_hash
from app.models.audit import AuditLog

router = APIRouter(prefix="/employees")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["admin", "hr_admin"])

def clean_str(val):
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
    return str(val).strip()


def resolve_dept_and_desig(
    db: Session,
    department_id: Optional[int] = None,
    designation_id: Optional[int] = None,
    department_str: str = "",
    designation_str: str = ""
):
    dept_id = None
    desig_id = None

    if department_id and department_id > 0:
        dept_id = department_id
    elif department_str and department_str.strip():
        clean_dept = department_str.strip()
        dept = db.query(Department).filter(Department.name == clean_dept).first()
        if not dept:
            dept = Department(name=clean_dept)
            db.add(dept)
            db.flush()
        dept_id = dept.id

    if designation_id and designation_id > 0:
        desig_id = designation_id
    elif designation_str and designation_str.strip():
        clean_desig = designation_str.strip()
        desig = db.query(Designation).filter(Designation.title == clean_desig).first()
        if not desig:
            desig = Designation(title=clean_desig, department_id=dept_id)
            db.add(desig)
            db.flush()
        desig_id = desig.id

    return dept_id, desig_id


@router.get("/", response_class=HTMLResponse)
async def list_employees(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    employees = db.query(Employee).all()
    return templates.TemplateResponse(
        request=request, name="employees/list.html", context={"user": current_user, "employees": employees}
    )


@router.get("/create", response_class=HTMLResponse)
async def create_employee_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    departments = db.query(Department).all()
    designations = db.query(Designation).all()
    return templates.TemplateResponse(
        request=request,
        name="employees/create_or_edit.html",
        context={
            "user": current_user,
            "employee": None,
            "departments": departments,
            "designations": designations,
        },
    )


@router.post("/create")
async def create_employee(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    department_id: Optional[int] = Form(None),
    designation_id: Optional[int] = Form(None),
    department: str = Form(""),
    designation: str = Form(""),
    base_salary: float = Form(0.0),
    hra: float = Form(0.0),
    custom_allowances: float = Form(0.0),
    pf_deduction: float = Form(0.0),
    tax_deduction: float = Form(0.0),
    phone_number: str = Form(None),
    home_address: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    country: str = Form(None),
    gender: str = Form(None),
    qualification: str = Form(None),
    experience: str = Form(None),
    emergency_contact: str = Form(None),
    emergency_contact_name: str = Form(None),
    emergency_contact_relation: str = Form(None),
    aadhar_number: str = Form(None),
    pan_number: str = Form(None),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    ifsc_code: str = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    hashed_password = get_password_hash(password)
    resolved_dept_id, resolved_desig_id = resolve_dept_and_desig(
        db, department_id, designation_id, department, designation
    )

    # 1. Create Core Employee
    emp = Employee(
        name=name,
        email=email,
        hashed_password=hashed_password,
        role=role,
        department_id=resolved_dept_id,
        designation_id=resolved_desig_id,
    )
    db.add(emp)
    db.flush()

    # 2. Create Profile
    profile = EmployeeProfile(
        employee_id=emp.id,
        phone_number=phone_number,
        home_address=home_address,
        city=city,
        state=state,
        country=country,
        gender=gender,
        qualification=qualification,
        experience=experience,
        aadhar_number=aadhar_number,
        pan_number=pan_number,
    )
    db.add(profile)

    # 3. Create Bank Details
    if bank_name or account_number or ifsc_code:
        bank = EmployeeBankAccount(
            employee_id=emp.id,
            bank_name=bank_name,
            account_number=account_number,
            ifsc_code=ifsc_code,
        )
        db.add(bank)

    # 4. Create Emergency Contact
    if emergency_contact or emergency_contact_name or emergency_contact_relation:
        contact = EmployeeEmergencyContact(
            employee_id=emp.id,
            contact_name=emergency_contact_name,
            relationship=emergency_contact_relation,
            phone_number=emergency_contact,
            is_primary=True,
        )
        db.add(contact)

    # 5. Create Salary Structure
    salary = SalaryStructure(
        employee_id=emp.id,
        base_salary=base_salary,
        hra=hra,
        custom_allowances=custom_allowances,
        pf_deduction=pf_deduction,
        tax_deduction=tax_deduction,
    )
    db.add(salary)

    db.commit()
    return RedirectResponse(url="/employees", status_code=302)



@router.get("/{emp_id}/view", response_class=HTMLResponse)
async def view_employee(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role not in ["admin", "hr_admin"] and current_user.id != emp_id:
        raise HTTPException(status_code=403, detail="Operation not permitted")
        
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    return templates.TemplateResponse(
        request=request, name="employees/view.html", context={"user": current_user, "employee": employee}
    )


@router.get("/{emp_id}/edit", response_class=HTMLResponse)
async def edit_employee_form(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role not in ["admin", "hr_admin"] and current_user.id != emp_id:
        raise HTTPException(status_code=403, detail="Operation not permitted")
        
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    departments = db.query(Department).all()
    designations = db.query(Designation).all()
    return templates.TemplateResponse(
        request=request,
        name="employees/create_or_edit.html",
        context={
            "user": current_user,
            "employee": employee,
            "departments": departments,
            "designations": designations,
        },
    )


@router.post("/{emp_id}/edit")
async def edit_employee(
    emp_id: int,
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(None),
    department_id: Optional[int] = Form(None),
    designation_id: Optional[int] = Form(None),
    department: str = Form(""),
    designation: str = Form(""),
    base_salary: float = Form(0.0),
    hra: float = Form(0.0),
    custom_allowances: float = Form(0.0),
    pf_deduction: float = Form(0.0),
    tax_deduction: float = Form(0.0),
    phone_number: str = Form(None),
    home_address: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    country: str = Form(None),
    gender: str = Form(None),
    qualification: str = Form(None),
    experience: str = Form(None),
    emergency_contact: str = Form(None),
    emergency_contact_name: str = Form(None),
    emergency_contact_relation: str = Form(None),
    aadhar_number: str = Form(None),
    pan_number: str = Form(None),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    ifsc_code: str = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role not in ["admin", "hr_admin"] and current_user.id != emp_id:
        raise HTTPException(status_code=403, detail="Operation not permitted")
        
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if employee:
        employee.name = name
        employee.email = email
        
        # Only Admins can modify role, department, designation, and salary components
        if current_user.role in ["admin", "hr_admin"]:
            old_role = employee.role
            if role:
                employee.role = role
                
            resolved_dept_id, resolved_desig_id = resolve_dept_and_desig(
                db, department_id, designation_id, department, designation
            )
            employee.department_id = resolved_dept_id
            employee.designation_id = resolved_desig_id
            
            # Salary Structure update
            if not employee.salary_structure:
                employee.salary_structure = SalaryStructure(employee_id=employee.id)
                db.add(employee.salary_structure)
            employee.salary_structure.base_salary = base_salary
            employee.salary_structure.hra = hra
            employee.salary_structure.custom_allowances = custom_allowances
            employee.salary_structure.pf_deduction = pf_deduction
            employee.salary_structure.tax_deduction = tax_deduction
            
            # Audit if role changed
            if role and old_role != role:
                audit = AuditLog(
                    actor_id=current_user.id,
                    actor_email=current_user.email,
                    action="ROLE_CHANGE",
                    entity="Employee",
                    entity_id=emp_id,
                    old_value=old_role,
                    new_value=role,
                )
                db.add(audit)
                
        # Profile Update
        if not employee.profile:
            employee.profile = EmployeeProfile(employee_id=employee.id)
            db.add(employee.profile)
        employee.profile.phone_number = phone_number
        employee.profile.home_address = home_address
        employee.profile.city = city
        employee.profile.state = state
        employee.profile.country = country
        employee.profile.gender = gender
        employee.profile.qualification = qualification
        employee.profile.experience = experience
        employee.profile.aadhar_number = aadhar_number
        employee.profile.pan_number = pan_number

        # Bank Account Update
        if not employee.bank_account:
            employee.bank_account = EmployeeBankAccount(employee_id=employee.id)
            db.add(employee.bank_account)
        employee.bank_account.bank_name = bank_name
        employee.bank_account.account_number = account_number
        employee.bank_account.ifsc_code = ifsc_code

        # Emergency Contact Update
        if not employee.emergency_contacts:
            contact = EmployeeEmergencyContact(employee_id=employee.id)
            employee.emergency_contacts.append(contact)
            db.add(contact)
        employee.emergency_contacts[0].contact_name = emergency_contact_name
        employee.emergency_contacts[0].relationship = emergency_contact_relation
        employee.emergency_contacts[0].phone_number = emergency_contact

        db.commit()

    return RedirectResponse(url=f"/employees/{emp_id}/view", status_code=302)



@router.post("/import")
async def import_employees(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin)
):
    contents = await file.read()
    wb = openpyxl.load_workbook(BytesIO(contents))
    sheet = wb.active
    
    imported_count = 0
    skipped_count = 0
    
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows) > 1:
        # Skip header row
        for row in rows[1:]:
            email = clean_str(row[2])
            if not email:
                continue
                
            # Check if exists
            existing = db.query(Employee).filter(Employee.email == email).first()
            if existing:
                skipped_count += 1
                continue
                
            full_name = clean_str(row[1])
            name = full_name if full_name else "Employee"
            
            phone = clean_str(row[3])
            password_plain = phone if phone else "Password@123"
            hashed_pw = get_password_hash(password_plain)
            
            emp = Employee(
                email=email,
                hashed_password=hashed_pw,
                name=name,
                role="employee",
            )
            db.add(emp)
            db.flush()

            profile = EmployeeProfile(
                employee_id=emp.id,
                phone_number=phone,
                home_address=clean_str(row[4]),
                city=clean_str(row[5]),
                state=clean_str(row[6]),
                country=clean_str(row[7]),
                gender=clean_str(row[8]),
                qualification=clean_str(row[9]),
                experience=clean_str(row[10]),
                aadhar_number=clean_str(row[14]),
                pan_number=clean_str(row[15]),
            )
            db.add(profile)

            bank = EmployeeBankAccount(
                employee_id=emp.id,
                bank_name=clean_str(row[16]),
                account_number=clean_str(row[17]),
                ifsc_code=clean_str(row[18]),
            )
            db.add(bank)

            contact = EmployeeEmergencyContact(
                employee_id=emp.id,
                contact_name=clean_str(row[12]),
                relationship=clean_str(row[13]),
                phone_number=clean_str(row[11]),
                is_primary=True,
            )
            db.add(contact)

            salary = SalaryStructure(
                employee_id=emp.id,
                base_salary=0.0,
                hra=0.0,
                custom_allowances=0.0,
                pf_deduction=0.0,
                tax_deduction=0.0,
            )
            db.add(salary)

            imported_count += 1
            
        db.commit()
        
    return RedirectResponse(url=f"/employees?imported={imported_count}&skipped={skipped_count}", status_code=302)


@router.post("/{emp_id}/reset-password")
async def admin_reset_password(
    emp_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.hashed_password = get_password_hash(new_password)
    
    # Record Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="ADMIN_PASSWORD_RESET",
        entity="Employee",
        entity_id=emp_id,
        old_value="[REDACTED]",
        new_value="[PASSWORD_RESET_BY_ADMIN]",
    )
    db.add(audit)
    db.commit()

    referer = request.headers.get("referer", f"/employees/{emp_id}/view")
    separator = "&" if "?" in referer else "?"
    if "reset_success=1" not in referer:
        referer = f"{referer}{separator}reset_success=1"
    return RedirectResponse(url=referer, status_code=302)
