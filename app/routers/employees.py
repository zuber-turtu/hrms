from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from io import BytesIO
import openpyxl

from app.database import get_db
from app.models.employee import Employee
from app.dependencies import require_auth, RoleChecker, get_password_hash
from app.models.audit import AuditLog

router = APIRouter(prefix="/employees")
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["super_admin", "hr_admin"])

def clean_str(val):
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
    return str(val).strip()



@router.get("/", response_class=HTMLResponse)
async def list_employees(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    employees = db.query(Employee).all()
    return templates.TemplateResponse(
        request, "employees/list.html", {"user": current_user, "employees": employees}
    )


@router.get("/create", response_class=HTMLResponse)
async def create_employee_form(
    request: Request,
    current_user: Employee = Depends(allow_hr_admin),
):
    return templates.TemplateResponse(
        request, "employees/create_or_edit.html", {"user": current_user, "employee": None}
    )


@router.post("/create")
async def create_employee(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
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
    emp = Employee(
        first_name=first_name,
        last_name=last_name,
        email=email,
        hashed_password=hashed_password,
        role=role,
        department=department,
        designation=designation,
        base_salary=base_salary,
        hra=hra,
        custom_allowances=custom_allowances,
        pf_deduction=pf_deduction,
        tax_deduction=tax_deduction,
        phone_number=phone_number,
        home_address=home_address,
        city=city,
        state=state,
        country=country,
        gender=gender,
        qualification=qualification,
        experience=experience,
        emergency_contact=emergency_contact,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_relation=emergency_contact_relation,
        aadhar_number=aadhar_number,
        pan_number=pan_number,
        bank_name=bank_name,
        account_number=account_number,
        ifsc_code=ifsc_code,
    )
    db.add(emp)
    db.commit()
    return RedirectResponse(url="/employees", status_code=302)



@router.get("/{emp_id}/view", response_class=HTMLResponse)
async def view_employee(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role not in ["super_admin", "hr_admin"] and current_user.id != emp_id:
        raise HTTPException(status_code=403, detail="Operation not permitted")
        
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    return templates.TemplateResponse(
        request, "employees/view.html", {"user": current_user, "employee": employee}
    )


@router.get("/{emp_id}/edit", response_class=HTMLResponse)
async def edit_employee_form(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    if current_user.role not in ["super_admin", "hr_admin"] and current_user.id != emp_id:
        raise HTTPException(status_code=403, detail="Operation not permitted")
        
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    return templates.TemplateResponse(
        request, "employees/create_or_edit.html", {"user": current_user, "employee": employee}
    )


@router.post("/{emp_id}/edit")
async def edit_employee(
    emp_id: int,
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(None),
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
    if current_user.role not in ["super_admin", "hr_admin"] and current_user.id != emp_id:
        raise HTTPException(status_code=403, detail="Operation not permitted")
        
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if employee:
        employee.first_name = first_name
        employee.last_name = last_name
        employee.email = email
        
        # Only Admins can modify role, department, designation, and salary components
        if current_user.role in ["super_admin", "hr_admin"]:
            old_role = employee.role
            # Keep previous role if not submitted or if it is empty
            if role:
                employee.role = role
            employee.department = department
            employee.designation = designation
            employee.base_salary = base_salary
            employee.hra = hra
            employee.custom_allowances = custom_allowances
            employee.pf_deduction = pf_deduction
            employee.tax_deduction = tax_deduction
            
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
                
        employee.phone_number = phone_number
        employee.home_address = home_address
        employee.city = city
        employee.state = state
        employee.country = country
        employee.gender = gender
        employee.qualification = qualification
        employee.experience = experience
        employee.emergency_contact = emergency_contact
        employee.emergency_contact_name = emergency_contact_name
        employee.emergency_contact_relation = emergency_contact_relation
        employee.aadhar_number = aadhar_number
        employee.pan_number = pan_number
        employee.bank_name = bank_name
        employee.account_number = account_number
        employee.ifsc_code = ifsc_code
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
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0] if name_parts[0] else "Employee"
            last_name = name_parts[1] if len(name_parts) > 1 else "User"
            
            phone = clean_str(row[3])
            # Default password is the phone number
            password_plain = phone if phone else "Password@123"
            hashed_pw = get_password_hash(password_plain)
            
            emp = Employee(
                email=email,
                hashed_password=hashed_pw,
                first_name=first_name,
                last_name=last_name,
                role="employee", # default role
                phone_number=phone,
                home_address=clean_str(row[4]),
                city=clean_str(row[5]),
                state=clean_str(row[6]),
                country=clean_str(row[7]),
                gender=clean_str(row[8]),
                qualification=clean_str(row[9]),
                experience=clean_str(row[10]),
                emergency_contact=clean_str(row[11]),
                emergency_contact_name=clean_str(row[12]),
                emergency_contact_relation=clean_str(row[13]),
                aadhar_number=clean_str(row[14]),
                pan_number=clean_str(row[15]),
                bank_name=clean_str(row[16]),
                account_number=clean_str(row[17]),
                ifsc_code=clean_str(row[18]),
            )
            db.add(emp)
            imported_count += 1
            
        db.commit()
        
    return RedirectResponse(url=f"/employees?imported={imported_count}&skipped={skipped_count}", status_code=302)
