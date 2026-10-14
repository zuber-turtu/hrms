from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, String, or_
from io import BytesIO
from collections import defaultdict
import datetime
import openpyxl
from typing import Optional, Union

from app.database import get_db
from app.models.employee import (
    Employee,
    EmployeeProfile,
    EmployeeBankAccount,
    EmployeeEmergencyContact,
    SalaryStructure,
)
from app.models.department import Department, Designation
from app.models.attendance import Attendance
from app.models.payroll import Payslip
from app.models.company import Company, CompanyZone
from app.dependencies import require_auth, RoleChecker, get_password_hash, create_access_token
from app.models.audit import AuditLog
from app.config import settings
from app.utils.timezone import get_ist_today, get_ist_now
from app.utils.security import get_safe_redirect
from app.services.storage import get_storage_provider
from app.templates_config import templates
from app.services.excel_exporter import export_employees_excel, export_employee_sample_template
import secrets
from app.services.email_service import (
    send_admin_password_reset_email,
    send_welcome_credentials_email,
    send_password_reset_email,
)
from app.utils.permissions import (
    can_manage_employee,
    can_assign_role,
    assert_can_manage_employee,
    assert_can_assign_role,
    get_role_rank,
)


router = APIRouter(prefix="/employees")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])

MAX_AVATAR_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

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

    if department_id:
        try:
            d_int = int(department_id)
            if d_int > 0:
                dept_id = d_int
        except (ValueError, TypeError):
            pass

    if not dept_id and department_str and department_str.strip():
        clean_dept = department_str.strip()
        dept = db.query(Department).filter(Department.name == clean_dept).first()
        if not dept:
            dept = Department(name=clean_dept)
            db.add(dept)
            db.flush()
        dept_id = dept.id

    if designation_id:
        try:
            ds_int = int(designation_id)
            if ds_int > 0:
                desig_id = ds_int
        except (ValueError, TypeError):
            pass

    if not desig_id and designation_str and designation_str.strip():
        clean_desig = designation_str.strip()
        desig = db.query(Designation).filter(Designation.title == clean_desig).first()
        if not desig:
            desig = Designation(title=clean_desig, department_id=dept_id)
            db.add(desig)
            db.flush()
        desig_id = desig.id

    return dept_id, desig_id


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def list_employees(
    request: Request,
    page: Optional[Union[int, str]] = 1,
    page_size: Optional[Union[int, str]] = 25,
    q: Optional[str] = None,
    role: Optional[str] = None,
    zone_id: Optional[Union[int, str]] = None,
    sort: Optional[str] = "name_asc",
    letter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    from app.utils.pagination import paginate_query

    try:
        page_num = int(page) if page is not None and str(page).strip().isdigit() else 1
    except (ValueError, TypeError):
        page_num = 1

    try:
        page_sz = int(page_size) if page_size is not None and str(page_size).strip().isdigit() else 25
    except (ValueError, TypeError):
        page_sz = 25

    parsed_zone_id: Optional[int] = None
    if zone_id is not None and str(zone_id).strip() and str(zone_id).strip().isdigit():
        parsed_zone_id = int(str(zone_id).strip())

    base_query = db.query(Employee)

    # Scoping for Managers: only employees in their department
    if current_user.role == "manager":
        base_query = base_query.filter(
            Employee.department_id == current_user.department_id,
            Employee.role.notin_(["super_admin", "admin", "hr", "hr_admin"])
        )
    # Scoping for HR: restricted strictly to their assigned zone if hr_zone_scope is 'zone_only'
    elif current_user.role in ["hr", "hr_admin"] and getattr(current_user, "hr_zone_scope", "all") == "zone_only" and current_user.zone_id:
        base_query = base_query.filter(
            Employee.zone_id == current_user.zone_id,
            Employee.role.notin_(["super_admin", "admin"])
        )

    # Calculate letter counts for active A-Z indicators directly in SQL (no full table load)
    total_scoped_count = base_query.count()
    first_char_expr = func.upper(func.substr(func.trim(Employee.name), 1, 1))
    raw_counts = base_query.with_entities(first_char_expr, func.count(Employee.id)).group_by(first_char_expr).all()
    letter_counts = defaultdict(int)
    for char, cnt in raw_counts:
        if char and 'A' <= char <= 'Z':
            letter_counts[char] += cnt
        elif char:
            letter_counts['#'] += cnt

    query = base_query

    # Search filter (Name, Email, Dept, Designation, Employee ID)
    if q and q.strip():
        search_raw = q.strip()
        search_term = f"%{search_raw}%"
        
        id_conditions = []
        digits_only = "".join(filter(str.isdigit, search_raw))
        is_explicit_id = (
            search_raw.startswith("#") or 
            search_raw.lower().startswith("emp") or 
            search_raw.lower().startswith("pay") or
            (digits_only and len(digits_only) > 1 and digits_only.startswith("0"))
        )

        if digits_only:
            try:
                emp_id_num = int(digits_only)
                id_conditions.append(Employee.id == emp_id_num)
            except ValueError:
                pass

        if not is_explicit_id:
            id_conditions.append(cast(Employee.id, String).ilike(search_term))
            if digits_only and len(digits_only) < 4:
                id_conditions.append(cast(Employee.id, String).ilike(f"%{digits_only.lstrip('0') or '0'}%"))

        query = query.outerjoin(Department, Employee.department_id == Department.id)\
                     .outerjoin(Designation, Employee.designation_id == Designation.id)\
                     .filter(
                         (Employee.name.ilike(search_term)) |
                         (Employee.email.ilike(search_term)) |
                         (Department.name.ilike(search_term)) |
                         (Designation.title.ilike(search_term)) |
                         or_(*id_conditions)
                     )

    # Role filter
    if role and role.strip() and role.strip() != "all":
        r = role.strip().lower()
        query = query.filter(func.lower(Employee.role) == r)

    # Zone filter
    if parsed_zone_id:
        query = query.filter(Employee.zone_id == parsed_zone_id)

    # Alphabetical letter filter
    selected_letter = (letter or "").strip().upper()
    if selected_letter and selected_letter != "ALL":
        if selected_letter == "#":
            # Filter non-alphabet characters
            for alpha_char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                query = query.filter(~Employee.name.ilike(f"{alpha_char}%"))
        else:
            query = query.filter(Employee.name.ilike(f"{selected_letter}%"))

    # Sorting options
    sort_mode = (sort or "name_asc").lower().strip()
    if sort_mode == "name_desc":
        query = query.order_by(func.lower(Employee.name).desc())
    elif sort_mode == "dept_asc":
        query = query.outerjoin(Department, Employee.department_id == Department.id).order_by(func.lower(Department.name).asc(), func.lower(Employee.name).asc())
    elif sort_mode == "dept_desc":
        query = query.outerjoin(Department, Employee.department_id == Department.id).order_by(func.lower(Department.name).desc(), func.lower(Employee.name).asc())
    elif sort_mode == "role_asc":
        query = query.order_by(Employee.role.asc(), func.lower(Employee.name).asc())
    elif sort_mode == "id_desc":
        query = query.order_by(Employee.id.desc())
    elif sort_mode == "id_asc":
        query = query.order_by(Employee.id.asc())
    else:  # default: name_asc (A-Z)
        query = query.order_by(func.lower(Employee.name).asc())

    page_data = paginate_query(query, page=page_num, page_size=page_sz)

    zones = db.query(CompanyZone).filter(CompanyZone.is_active == True).order_by(CompanyZone.name.asc()).all()

    context = {
        "request": request,
        "user": current_user,
        "page_data": page_data,
        "employees": page_data.items,
        "total_employees_count": total_scoped_count,
        "letter_counts": dict(letter_counts),
        "current_sort": sort_mode,
        "current_letter": selected_letter if selected_letter else "ALL",
        "current_role": (role.strip().lower() if role and role.strip() else "all"),
        "current_zone_id": parsed_zone_id,
        "zones": zones,
        "current_q": q or "",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="employees/partials/_table_rows.html",
            context=context
        )

    return templates.TemplateResponse(
        request=request,
        name="employees/list.html",
        context=context
    )



@router.get("/create", response_class=HTMLResponse)
async def create_employee_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    departments = db.query(Department).all()
    designations = db.query(Designation).all()
    zones = db.query(CompanyZone).filter(CompanyZone.is_active == True).order_by(CompanyZone.name.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="employees/create_or_edit.html",
        context={
            "user": current_user,
            "employee": None,
            "departments": departments,
            "designations": designations,
            "zones": zones,
            "today": get_ist_today(),
        },
    )


@router.post("/create")
async def create_employee(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    personal_email: Optional[str] = Form(None),
    company_email: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    zone_id: Optional[int] = Form(None),
    hr_zone_scope: Optional[str] = Form("all"),
    department_id: Optional[int] = Form(None),
    designation_id: Optional[int] = Form(None),
    joining_date: Optional[str] = Form(None),
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
    uan_number: str = Form(None),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    ifsc_code: str = Form(None),
    is_geofence_exempt: bool = Form(False),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    from urllib.parse import quote_plus

    # Hierarchical Privilege Escalation Defense: lower role cannot create/assign equal or higher role
    assert_can_assign_role(current_user, role)

    # Resolve and validate emails
    clean_personal = (personal_email or email or "").strip().lower()
    clean_company = company_email.strip().lower() if company_email and company_email.strip() else None

    if not clean_personal:
        return RedirectResponse(
            url=f"/employees/create?error={quote_plus('Personal email address is required.')}",
            status_code=302
        )

    # Check collision for personal email
    existing_personal = db.query(Employee).filter(
        or_(
            Employee.personal_email == clean_personal,
            Employee.company_email == clean_personal,
            Employee.email == clean_personal,
        )
    ).first()
    if existing_personal:
        return RedirectResponse(
            url=f"/employees/create?error={quote_plus(f'Email «{clean_personal}» is already registered to another account.')}",
            status_code=302
        )

    # Check collision for company email (if provided)
    if clean_company:
        existing_company = db.query(Employee).filter(
            or_(
                Employee.personal_email == clean_company,
                Employee.company_email == clean_company,
                Employee.email == clean_company,
            )
        ).first()
        if existing_company:
            return RedirectResponse(
                url=f"/employees/create?error={quote_plus(f'Company work email «{clean_company}» is already registered.')}",
                status_code=302
            )

    canonical_email = clean_company if clean_company else clean_personal

    hashed_password = get_password_hash(password)
    resolved_dept_id, resolved_desig_id = resolve_dept_and_desig(
        db, department_id, designation_id, department, designation
    )

    parsed_joining_date = get_ist_today()
    if joining_date and joining_date.strip():
        try:
            parsed_joining_date = datetime.datetime.strptime(joining_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_joining_date = get_ist_today()

    # 1. Create Core Employee
    emp = Employee(
        name=name.strip(),
        email=canonical_email,
        personal_email=clean_personal,
        company_email=clean_company,
        zone_id=zone_id,
        hr_zone_scope=hr_zone_scope or "all",
        hashed_password=hashed_password,
        role=role,
        department_id=resolved_dept_id,
        designation_id=resolved_desig_id,
        joining_date=parsed_joining_date,
    )
    db.add(emp)
    db.flush()

    # Handle Photo Upload if present
    avatar_url = None
    photo_file_id = None
    if photo and photo.filename:
        ext = photo.filename.split(".")[-1].lower() if "." in photo.filename else ""
        if ext in ALLOWED_AVATAR_EXTENSIONS:
            file_bytes = await photo.read(MAX_AVATAR_FILE_SIZE + 1)
            if 0 < len(file_bytes) <= MAX_AVATAR_FILE_SIZE:
                try:
                    storage = get_storage_provider()
                    avatar_url, photo_file_id = storage.upload_file(
                        file_bytes,
                        filename=photo.filename,
                        content_type=photo.content_type or "image/jpeg",
                        folder="avatars",
                    )
                except Exception as e:
                    print(f"[create_employee Photo Upload Error] {e}")

    # 2. Create Profile
    profile = EmployeeProfile(
        employee_id=emp.id,
        avatar_url=avatar_url,
        photo_file_id=photo_file_id,
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
        uan_number=uan_number,
        is_geofence_exempt=is_geofence_exempt,
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
    db.commit()

    # Dispatch welcome credentials email
    base_url = settings.APP_BASE_URL.rstrip("/") if settings.APP_BASE_URL else str(request.base_url).rstrip("/")
    login_url = f"{base_url}/login"
    background_tasks.add_task(
        send_welcome_credentials_email,
        to_email=emp.email,
        recipient_name=emp.name,
        password=password,
        login_url=login_url,
        role=emp.role,
    )

    return RedirectResponse(url="/employees", status_code=302)




@router.get("/export-excel")
async def export_employees(
    q: Optional[str] = None,
    dept_id: Optional[Union[int, str]] = None,
    zone_id: Optional[Union[int, str]] = None,
    role: Optional[str] = None,
    status: Optional[str] = "all",
    letter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Exports workforce roster to a styled Excel spreadsheet matching active filters."""
    query = db.query(Employee)

    parsed_zone_id: Optional[int] = None
    if zone_id is not None and str(zone_id).strip() and str(zone_id).strip().isdigit():
        parsed_zone_id = int(str(zone_id).strip())

    parsed_dept_id: Optional[int] = None
    if dept_id is not None and str(dept_id).strip() and str(dept_id).strip().isdigit():
        parsed_dept_id = int(str(dept_id).strip())

    if current_user.role != "super_admin":
        query = query.filter(Employee.role != "super_admin")

    if current_user.role == "manager":
        query = query.filter(Employee.department_id == current_user.department_id)
    elif current_user.role in ["hr", "hr_admin"] and getattr(current_user, "hr_zone_scope", "all") == "zone_only" and current_user.zone_id:
        query = query.filter(Employee.zone_id == current_user.zone_id)

    if q and q.strip():
        search_raw = q.strip()
        search_term = f"%{search_raw}%"
        id_conditions = []
        digits_only = "".join(filter(str.isdigit, search_raw))
        if digits_only:
            try:
                emp_id_num = int(digits_only)
                id_conditions.append(Employee.id == emp_id_num)
            except ValueError:
                pass
        id_conditions.append(cast(Employee.id, String).ilike(search_term))
        query = query.outerjoin(Department, Employee.department_id == Department.id)\
                     .outerjoin(Designation, Employee.designation_id == Designation.id)\
                     .filter(
                         (Employee.name.ilike(search_term)) |
                         (Employee.email.ilike(search_term)) |
                         (Department.name.ilike(search_term)) |
                         (Designation.title.ilike(search_term)) |
                         or_(*id_conditions)
                     )

    if parsed_dept_id and parsed_dept_id > 0:
        query = query.filter(Employee.department_id == parsed_dept_id)

    if parsed_zone_id and parsed_zone_id > 0:
        query = query.filter(Employee.zone_id == parsed_zone_id)

    if role and role.strip() and role.strip().lower() != "all":
        r = role.strip().lower()
        if r in ["hr", "hr_admin"]:
            query = query.filter(Employee.role.in_(["hr", "hr_admin"]))
        else:
            query = query.filter(func.lower(Employee.role) == r)

    if status and status.strip() and status.lower() != "all":
        if status.lower() == "active":
            query = query.filter(Employee.is_active == True)
        elif status.lower() == "inactive":
            query = query.filter(Employee.is_active == False)

    if letter and letter.strip() and letter.upper() != "ALL":
        query = query.filter(Employee.name.ilike(f"{letter.strip()}%"))

    employees = query.order_by(Employee.name.asc()).all()
    company = db.query(Company).first()
    return export_employees_excel(employees, company)


@router.get("/sample-template")
async def download_sample_template(
    current_user: Employee = Depends(allow_hr_admin),
):
    """Downloads sample employee import template spreadsheet."""
    return export_employee_sample_template()


@router.get("/{emp_id}", response_class=HTMLResponse)
@router.get("/{emp_id}/view", response_class=HTMLResponse)
async def view_employee(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Authorization Check:
    # 1. Self access is permitted
    # 2. Super Admin, Admin, and HR can view any employee record
    # 3. Managers can only view subordinate employees/interns within their own department
    if current_user.id != emp_id and current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
        if current_user.role == "manager":
            if (
                not current_user.department_id
                or employee.department_id != current_user.department_id
                or employee.role in ["super_admin", "admin", "hr", "hr_admin"]
            ):
                raise HTTPException(status_code=403, detail="Operation not permitted")
        else:
            raise HTTPException(status_code=403, detail="Operation not permitted")

    # 1. Fetch payslips for this employee
    payslips = (
        db.query(Payslip)
        .filter(Payslip.employee_id == emp_id)
        .order_by(Payslip.year.desc(), Payslip.month.desc())
        .all()
    )

    # 2. Fetch and group attendance logs for this employee (only for non-super-admin workforce)
    attendance_data = []
    if employee.role != "super_admin":
        raw_logs = (
            db.query(Attendance)
            .filter(Attendance.employee_id == emp_id)
            .order_by(Attendance.date.desc(), Attendance.check_in.desc(), Attendance.id.desc())
            .all()
        )
        grouped = defaultdict(list)
        for log in raw_logs:
            grouped[log.date].append(log)

        today = get_ist_today()
        now_ist = get_ist_now()
        for date, group_logs in grouped.items():
            total_seconds = 0
            sessions = []
            is_overridden = False
            override_reason = ""
            is_missed = False
            for log in group_logs:
                if log.is_overridden:
                    is_overridden = True
                    override_reason = log.override_reason
                start = log.check_in
                if log.check_out:
                    end = log.check_out
                    out_str = log.check_out.strftime('%I:%M %p')
                else:
                    if log.date < today:
                        end = log.check_in
                        out_str = "Missed"
                        is_missed = True
                    else:
                        end = now_ist
                        out_str = "Active"
                diff = (end - start).total_seconds()
                total_seconds += max(0, diff)
                in_str = log.check_in.strftime('%I:%M %p')
                sessions.append(f"{in_str} - {out_str}")
                
            hrs = int(total_seconds // 3600)
            mins = int((total_seconds % 3600) // 60)
            secs = int(total_seconds % 60)
            total_active_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

            # Latest punch session is at index 0 due to check_in.desc()
            latest_log = group_logs[0]
            latest_dist = latest_log.check_in_distance_m if latest_log.check_in_distance_m is not None else latest_log.check_out_distance_m
            latest_in_range = latest_log.check_in_in_range if latest_log.check_in_in_range is not None else latest_log.check_out_in_range
            is_exempt = bool(employee and employee.profile and employee.profile.is_geofence_exempt)
            loc_name = latest_log.check_in_location_name or latest_log.check_out_location_name

            attendance_data.append({
                "id": latest_log.id,
                "date": date,
                "sessions": ", ".join(sessions),
                "total_active": f"{total_active_str} (Missed)" if is_missed else total_active_str,
                "is_overridden": is_overridden,
                "override_reason": override_reason,
                "is_missed": is_missed,
                "check_in": latest_log.check_in,
                "check_out": latest_log.check_out,
                "distance_m": latest_dist,
                "in_range": latest_in_range,
                "is_exempt": is_exempt,
                "location_name": loc_name,
            })
        
    # 3. Fetch Document & KYC checklist
    from app.routers.documents import get_employee_document_checklist
    doc_data = get_employee_document_checklist(employee, db)

    # 4. Fetch Leave Entitlements, Quotas & History
    from app.routers.leaves import ensure_employee_leave_balances, auto_lapse_pending_requests
    from app.models.leave import LeaveApplication, WfhRequest
    auto_lapse_pending_requests(db)
    current_year = get_ist_today().year
    employee_leave_balances = ensure_employee_leave_balances(db, emp_id, current_year)
    employee_leaves = (
        db.query(LeaveApplication)
        .filter(LeaveApplication.employee_id == emp_id)
        .order_by(LeaveApplication.created_at.desc())
        .all()
    )
    employee_wfh = (
        db.query(WfhRequest)
        .filter(WfhRequest.employee_id == emp_id)
        .order_by(WfhRequest.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="employees/view.html",
        context={
            "user": current_user,
            "employee": employee,
            "payslips": payslips,
            "attendance_logs": attendance_data,
            "doc_checklist": doc_data["checklist"],
            "doc_unmapped": doc_data["unmapped_docs"],
            "doc_summary": doc_data,
            "leave_balances": employee_leave_balances,
            "employee_leaves": employee_leaves,
            "employee_wfh": employee_wfh,
            "current_year": current_year,
        },
    )


@router.get("/{emp_id}/edit", response_class=HTMLResponse)
async def edit_employee_form(
    emp_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if current_user.id != emp_id:
        if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
            raise HTTPException(status_code=403, detail="Operation not permitted")
        assert_can_manage_employee(current_user, employee, "edit")

        
    departments = db.query(Department).all()
    designations = db.query(Designation).all()
    zones = db.query(CompanyZone).filter(CompanyZone.is_active == True).order_by(CompanyZone.name.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="employees/create_or_edit.html",
        context={
            "user": current_user,
            "employee": employee,
            "departments": departments,
            "designations": designations,
            "zones": zones,
            "today": get_ist_today(),
        },
    )


@router.post("/{emp_id}/edit")
async def edit_employee(
    emp_id: int,
    request: Request,
    name: str = Form(...),
    personal_email: Optional[str] = Form(None),
    company_email: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    zone_id: Optional[int] = Form(None),
    hr_zone_scope: Optional[str] = Form("all"),
    role: str = Form(None),
    department_id: Optional[int] = Form(None),
    designation_id: Optional[int] = Form(None),
    joining_date: Optional[str] = Form(None),
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
    uan_number: str = Form(None),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    ifsc_code: str = Form(None),
    is_geofence_exempt: bool = Form(False),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    from urllib.parse import quote_plus

    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    clean_role = role.strip().lower() if role and role.strip() else None

    # Hierarchical Protection: Self-edit vs Administrative edit
    if current_user.id == emp_id:
        if clean_role and clean_role != employee.role.strip().lower():
            raise HTTPException(status_code=403, detail="Operation not permitted: You cannot change your own role.")
    else:
        if current_user.role not in ["super_admin", "admin", "hr", "hr_admin"]:
            raise HTTPException(status_code=403, detail="Operation not permitted")
        assert_can_manage_employee(current_user, employee, "modify")
        if clean_role and clean_role != employee.role.strip().lower():
            assert_can_assign_role(current_user, clean_role)


    # Resolve emails
    clean_personal = (personal_email or email or employee.personal_email or employee.email or "").strip().lower()
    clean_company = company_email.strip().lower() if company_email and company_email.strip() else None

    # Check for email collisions with other accounts
    if clean_personal:
        existing_personal = db.query(Employee).filter(
            or_(
                Employee.personal_email == clean_personal,
                Employee.company_email == clean_personal,
                Employee.email == clean_personal,
            ),
            Employee.id != emp_id
        ).first()
        if existing_personal:
            return RedirectResponse(
                url=f"/employees/{emp_id}/edit?error={quote_plus(f'Personal email «{clean_personal}» is already in use by another account.')}",
                status_code=302
            )

    if clean_company:
        existing_company = db.query(Employee).filter(
            or_(
                Employee.personal_email == clean_company,
                Employee.company_email == clean_company,
                Employee.email == clean_company,
            ),
            Employee.id != emp_id
        ).first()
        if existing_company:
            return RedirectResponse(
                url=f"/employees/{emp_id}/edit?error={quote_plus(f'Company work email «{clean_company}» is already in use by another account.')}",
                status_code=302
            )

    canonical_email = clean_company if clean_company else clean_personal
    employee.name = name.strip()
    employee.personal_email = clean_personal
    employee.company_email = clean_company
    employee.email = canonical_email
    
    # Only administrative actors who have hierarchical authority over this target can modify role, department, designation, joining_date, and salary components
    if current_user.id != emp_id and can_manage_employee(current_user, employee):
        old_role = employee.role
        if clean_role and clean_role != employee.role:
            assert_can_assign_role(current_user, clean_role)
            employee.role = clean_role
            
        resolved_dept_id, resolved_desig_id = resolve_dept_and_desig(
            db, department_id, designation_id, department, designation
        )
        employee.department_id = resolved_dept_id
        employee.designation_id = resolved_desig_id
        employee.zone_id = zone_id

        # HR Zone Scoping permissions
        if current_user.role in ["super_admin", "admin"]:
            employee.hr_zone_scope = hr_zone_scope or "all"
        elif current_user.role in ["hr", "hr_admin"] and hr_zone_scope and employee.role not in ["super_admin", "admin"]:
            employee.hr_zone_scope = hr_zone_scope
        
        # Joining Date update
        if joining_date and joining_date.strip():
            try:
                new_joining_date = datetime.datetime.strptime(joining_date.strip(), "%Y-%m-%d").date()
                old_joining_date = employee.joining_date
                if old_joining_date != new_joining_date:
                    employee.joining_date = new_joining_date
                    audit = AuditLog(
                        actor_id=current_user.id,
                        actor_email=current_user.email,
                        action="JOINING_DATE_CHANGE",
                        entity="Employee",
                        entity_id=emp_id,
                        old_value=str(old_joining_date) if old_joining_date else "None",
                        new_value=str(new_joining_date),
                    )
                    db.add(audit)
            except ValueError:
                pass

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
    employee.profile.uan_number = uan_number
    
    if current_user.role in ["super_admin", "admin", "hr", "hr_admin"]:
        employee.profile.is_geofence_exempt = is_geofence_exempt

    # Handle Photo Upload if present
    if photo and photo.filename:
        ext = photo.filename.split(".")[-1].lower() if "." in photo.filename else ""
        if ext not in ALLOWED_AVATAR_EXTENSIONS:
            return RedirectResponse(
                url=f"/employees/{emp_id}/edit?error=Invalid+image+format.+Allowed+formats:+JPG,+PNG,+WEBP.",
                status_code=302
            )
        file_bytes = await photo.read(MAX_AVATAR_FILE_SIZE + 1)
        if len(file_bytes) > MAX_AVATAR_FILE_SIZE:
            return RedirectResponse(
                url=f"/employees/{emp_id}/edit?error=Avatar+image+exceeds+the+maximum+allowed+size+of+2MB.",
                status_code=302
            )
        if len(file_bytes) > 0:
            try:
                storage = get_storage_provider()
                avatar_url, photo_file_id = storage.upload_file(
                    file_bytes,
                    filename=photo.filename,
                    content_type=photo.content_type or "image/jpeg",
                    folder="avatars",
                )
                employee.profile.avatar_url = avatar_url
                employee.profile.photo_file_id = photo_file_id
            except Exception as e:
                pass

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

    response = RedirectResponse(url=f"/employees/{emp_id}/view", status_code=302)
    if current_user.id == emp_id and email != current_user.email:
        access_token_expires = datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        new_token = create_access_token(
            data={"sub": employee.email}, expires_delta=access_token_expires
        )
        response.set_cookie(
            key=settings.COOKIE_NAME,
            value=new_token,
            httponly=True,
            samesite=settings.COOKIE_SAMESITE,
            secure=settings.COOKIE_SECURE,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            expires=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    return response



MAX_IMPORT_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


@router.post("/import")
async def import_employees(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin)
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return RedirectResponse(
            url="/employees?error=Invalid+file+format.+Only+.xlsx+spreadsheets+are+allowed.",
            status_code=302
        )

    contents = await file.read(MAX_IMPORT_FILE_SIZE + 1)
    if len(contents) > MAX_IMPORT_FILE_SIZE:
        return RedirectResponse(
            url="/employees?error=File+exceeds+the+maximum+allowed+size+of+2MB.",
            status_code=302
        )

    try:
        wb = openpyxl.load_workbook(BytesIO(contents), data_only=True)
        sheet = wb.active
    except Exception:
        return RedirectResponse(
            url="/employees?error=Could+not+parse+the+uploaded+Excel+file.+Please+ensure+it+is+a+valid+.xlsx+spreadsheet.",
            status_code=302
        )
    
    imported_count = 0
    skipped_count = 0
    seen_emails_in_batch = set()
    
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows) > 1:
        # Skip header row
        for row in rows[1:]:
            email = clean_str(row[2]).strip().lower()
            if not email:
                continue
            
            # Check 1: Duplicate inside the uploaded Excel sheet itself
            if email in seen_emails_in_batch:
                skipped_count += 1
                continue
            seen_emails_in_batch.add(email)
                
            # Check 2: Duplicate in Database (Employee already exists by email)
            existing = db.query(Employee).filter(func.lower(Employee.email) == email).first()
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
                uan_number=clean_str(row[19]) if len(row) > 19 else None,
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

        # Audit Log entry for the batch import
        audit = AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="BULK_EMPLOYEE_IMPORT",
            entity="Employee",
            entity_id=0,
            old_value="[EXCEL_FILE_UPLOAD]",
            new_value=f"Imported {imported_count} new employees, skipped {skipped_count} duplicates",
        )
        db.add(audit)
        db.commit()
        
    return RedirectResponse(url=f"/employees?imported={imported_count}&skipped={skipped_count}", status_code=302)


@router.post("/{emp_id}/reset-password")
async def admin_reset_password(
    emp_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    reset_mode: str = Form("direct"),
    new_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Hierarchical Privilege Enforcement: Lower role cannot reset credentials for equal or higher roles
    assert_can_manage_employee(current_user, employee, "reset credentials for")

    base_url = settings.APP_BASE_URL.rstrip("/") if settings.APP_BASE_URL else str(request.base_url).rstrip("/")
    safe_target = get_safe_redirect(request, default=f"/employees/{emp_id}/view")
    separator = "&" if "?" in safe_target else "?"

    # Higher Authority Option A: Send Password Reset Verification Link via Email
    if reset_mode == "email_link" or not new_password:
        token = secrets.token_urlsafe(32)
        expire_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=expire_minutes)

        employee.reset_token = token
        employee.reset_token_expiry = expiry
        db.commit()

        reset_url = f"{base_url}/reset-password?token={token}"
        background_tasks.add_task(
            send_password_reset_email,
            to_email=employee.email,
            recipient_name=employee.name,
            reset_url=reset_url,
        )

        audit = AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="ADMIN_SENT_PASSWORD_RESET_LINK",
            entity="Employee",
            entity_id=emp_id,
            old_value=None,
            new_value=f"Verification reset link dispatched to {employee.email}",
        )
        db.add(audit)
        db.commit()

        redirect_url = f"{safe_target}{separator}reset_email_sent=1"
        return RedirectResponse(url=redirect_url, status_code=302)

    # Higher Authority Option B: Directly Set New Password & Email Employee
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters long.")

    employee.hashed_password = get_password_hash(new_password)
    employee.reset_token = None
    employee.reset_token_expiry = None
    
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

    login_url = f"{base_url}/login"
    background_tasks.add_task(
        send_admin_password_reset_email,
        to_email=employee.email,
        recipient_name=employee.name,
        new_password=new_password,
        login_url=login_url,
    )

    if "reset_success=1" not in safe_target:
        redirect_url = f"{safe_target}{separator}reset_success=1"
    else:
        redirect_url = safe_target
    return RedirectResponse(url=redirect_url, status_code=302)


# =========================================================================
# EXCEL EXPORT & TEMPLATE ENDPOINTS

