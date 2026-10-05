import json
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from urllib.parse import quote_plus

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.templates_config import templates
from app.utils.permissions import AVAILABLE_PERMISSIONS, get_company_permissions

router = APIRouter(prefix="/company")

allow_hr_admin = RoleChecker(["admin", "hr_admin"])


@router.get("/profile", response_class=HTMLResponse)
async def company_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = db.query(Company).first()
    if not company:
        company = Company()
        db.add(company)
        db.commit()
        db.refresh(company)

    employees = (
        db.query(Employee)
        .order_by(Employee.name.asc())
        .all()
    )

    permissions_matrix = get_company_permissions(company)
    
    dept_set = set()
    for emp in employees:
        if emp.department:
            d_name = emp.department.name if hasattr(emp.department, "name") else str(emp.department)
            if d_name and d_name.strip():
                dept_set.add(d_name.strip())
    departments = sorted(list(dept_set))

    return templates.TemplateResponse(
        request,
        "company/profile.html",
        {
            "user": current_user,
            "company": company,
            "employees": employees,
            "departments": departments,
            "available_permissions": AVAILABLE_PERMISSIONS,
            "permissions_matrix": permissions_matrix,
        }
    )


@router.post("/profile")
async def update_company_profile(
    request: Request,
    section: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    tagline: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    support_email: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    logo_url: Optional[str] = Form(None),
    employee_id_prefix: Optional[str] = Form(None),
    currency_symbol: Optional[str] = Form(None),
    currency_code: Optional[str] = Form(None),
    working_days_per_month: Optional[int] = Form(None),
    standard_hours_per_day: Optional[float] = Form(None),
    half_day_threshold_hours: Optional[float] = Form(None),
    lunch_break_hours: Optional[float] = Form(None),
    lunch_start_time: Optional[str] = Form(None),
    lunch_end_time: Optional[str] = Form(None),
    cin: Optional[str] = Form(None),
    gstin: Optional[str] = Form(None),
    pan: Optional[str] = Form(None),
    office_latitude: Optional[str] = Form(None),
    office_longitude: Optional[str] = Form(None),
    geofence_radius_meters: Optional[int] = Form(None),
    geofence_enabled: Optional[bool] = Form(False),
    geofence_strict_mode: Optional[bool] = Form(False),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    company = db.query(Company).first()
    if not company:
        company = Company()
        db.add(company)

    msg = "Company settings updated successfully"

    form_data = await request.form()

    if section == "branding" or section is None:
        if "name" in form_data:
            company.name = form_data["name"].strip() if form_data["name"].strip() else "Acme Corp"
        elif name is not None:
            company.name = name.strip() if name.strip() else "Acme Corp"

        if "tagline" in form_data:
            company.tagline = form_data["tagline"].strip() if form_data["tagline"].strip() else None
        elif tagline is not None:
            company.tagline = tagline.strip() if tagline.strip() else None

        if "address" in form_data:
            company.address = form_data["address"].strip()
        elif address is not None:
            company.address = address.strip()

        if "support_email" in form_data:
            company.support_email = form_data["support_email"].strip() if form_data["support_email"].strip() else None
        elif support_email is not None:
            company.support_email = support_email.strip() if support_email.strip() else None

        if "website" in form_data:
            company.website = form_data["website"].strip() if form_data["website"].strip() else None
        elif website is not None:
            company.website = website.strip() if website.strip() else None

        if "logo_url" in form_data:
            company.logo_url = form_data["logo_url"].strip() if form_data["logo_url"].strip() else None
        elif logo_url is not None:
            company.logo_url = logo_url.strip() if logo_url.strip() else None

        if "employee_id_prefix" in form_data:
            p_val = form_data["employee_id_prefix"].strip()
            company.employee_id_prefix = p_val.upper() if p_val else None
        elif employee_id_prefix is not None:
            company.employee_id_prefix = employee_id_prefix.strip().upper() if employee_id_prefix.strip() else None

        if section == "branding":
            msg = "Corporate branding & identity updated successfully"

    if section == "schedule" or section is None:
        if working_days_per_month is not None:
            company.working_days_per_month = working_days_per_month
        if standard_hours_per_day is not None:
            company.standard_hours_per_day = standard_hours_per_day
        if half_day_threshold_hours is not None:
            company.half_day_threshold_hours = half_day_threshold_hours
        if lunch_break_hours is not None:
            company.lunch_break_hours = lunch_break_hours
        if lunch_start_time is not None:
            company.lunch_start_time = lunch_start_time.strip() if lunch_start_time.strip() else "13:00"
        if lunch_end_time is not None:
            company.lunch_end_time = lunch_end_time.strip() if lunch_end_time.strip() else "14:00"
        if section == "schedule":
            msg = "Work schedule, shifts & lunch policy updated successfully"

    if section == "payroll" or section is None:
        if currency_symbol is not None:
            company.currency_symbol = currency_symbol.strip() if currency_symbol.strip() else "$"
        if currency_code is not None:
            company.currency_code = currency_code.strip().upper() if currency_code.strip() else "USD"
        if working_days_per_month is not None and section == "payroll":
            company.working_days_per_month = working_days_per_month
        if section == "payroll":
            msg = "Payroll & currency settings updated successfully"

    if section == "statutory" or section is None:
        if cin is not None:
            company.cin = cin.strip().upper() if cin.strip() else None
        if gstin is not None:
            company.gstin = gstin.strip().upper() if gstin.strip() else None
        if pan is not None:
            company.pan = pan.strip().upper() if pan.strip() else None
        if section == "statutory":
            msg = "Statutory & tax compliance identification updated successfully"

    if section == "geofence" or section is None:
        if office_latitude is not None:
            if office_latitude.strip():
                try:
                    company.office_latitude = float(office_latitude.strip())
                except ValueError:
                    company.office_latitude = None
            else:
                company.office_latitude = None

        if office_longitude is not None:
            if office_longitude.strip():
                try:
                    company.office_longitude = float(office_longitude.strip())
                except ValueError:
                    company.office_longitude = None
            else:
                company.office_longitude = None

        if geofence_radius_meters is not None:
            company.geofence_radius_meters = max(10, int(geofence_radius_meters))
        if section == "geofence" or (geofence_enabled is not None):
            company.geofence_enabled = bool(geofence_enabled)
        if section == "geofence" or (geofence_strict_mode is not None):
            company.geofence_strict_mode = bool(geofence_strict_mode)
        if section == "geofence":
            msg = "Office geofencing & perimeter settings updated successfully"

    if section == "permissions":
        form_data = await request.form()
        current_matrix = get_company_permissions(company)
        
        for role in ["hr_admin", "manager", "employee", "intern"]:
            for perm in AVAILABLE_PERMISSIONS:
                k = perm["key"]
                form_key = f"perm_{role}_{k}"
                is_checked = bool(form_key in form_data and form_data[form_key] in ["true", "1", "on", "yes"])
                current_matrix[role][k] = is_checked

        company.role_permissions = json.dumps(current_matrix)
        msg = "Dynamic role permissions matrix updated successfully"

    db.commit()

    tab_redirect = section if section else "branding"
    return RedirectResponse(url=f"/company/profile?tab={tab_redirect}&success={quote_plus(msg)}", status_code=302)


@router.post("/assign-role")
async def assign_employee_role(
    request: Request,
    employee_id: int = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    valid_roles = ["admin", "hr_admin", "manager", "employee", "intern"]
    role_clean = role.strip().lower()
    if role_clean not in valid_roles:
        raise HTTPException(status_code=400, detail="Invalid system role")

    target_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not target_employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    old_role = target_employee.role
    target_employee.role = role_clean

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="ROLE_ASSIGNMENT",
        entity="Employee",
        entity_id=target_employee.id,
        old_value=f"Role: {old_role}",
        new_value=f"Role: {role_clean}",
    )
    db.add(audit)
    db.commit()

    if request.headers.get("HX-Request"):
        role_badges = {
            "admin": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-purple-50 text-purple-700 border border-purple-200">Super Admin</span>',
            "hr_admin": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-teal-50 text-teal-700 border border-teal-200">HR Admin</span>',
            "manager": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">Manager</span>',
            "intern": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">Intern</span>',
            "employee": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">Employee</span>',
        }
        badge_html = role_badges.get(role_clean, role_badges["employee"])
        initials = (target_employee.name[:2] if target_employee.name else "EM").upper()
        dept = target_employee.department.name if hasattr(target_employee.department, "name") else (str(target_employee.department) if target_employee.department else "Unassigned")
        desig = target_employee.designation.name if hasattr(target_employee.designation, "name") else (str(target_employee.designation) if target_employee.designation else "Staff")
        
        options = []
        for r_val, r_label in [
            ("employee", "Employee"),
            ("intern", "Intern"),
            ("manager", "Manager"),
            ("hr_admin", "HR Admin"),
            ("admin", "Super Admin"),
        ]:
            selected = "selected" if r_val == role_clean else ""
            options.append(f'<option value="{r_val}" {selected}>{r_label}</option>')
        options_html = "\n".join(options)

        company = db.query(Company).first()
        prefix = company.employee_id_prefix.strip() if (company and company.employee_id_prefix) else ""
        emp_code = f"{prefix.upper()}-{target_employee.id:04d}" if prefix else f"#{target_employee.id:04d}"

        row_html = f'''
        <tr class="hover:bg-slate-50/60 transition-colors role-assign-row bg-emerald-50/40" id="role-row-{target_employee.id}" data-name="{target_employee.name.lower()}" data-dept="{dept.lower()}" data-role="{role_clean}" data-email="{target_employee.email.lower()}">
            <td class="py-3 px-4">
                <div class="flex items-center space-x-2.5">
                    <div class="w-8 h-8 rounded-full bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-xs border border-slate-200 shrink-0">
                        {initials}
                    </div>
                    <div>
                        <div class="font-bold text-slate-900 flex items-center space-x-1.5">
                            <span>{target_employee.name}</span>
                            <span class="inline-flex items-center text-[10px] font-semibold text-emerald-700 bg-emerald-100/80 px-1.5 py-0.5 rounded animate-pulse">✓ Updated</span>
                        </div>
                        <div class="text-[11px] text-slate-400">{target_employee.email} &bull; <span class="font-mono text-slate-500">{emp_code}</span></div>
                    </div>
                </div>
            </td>
            <td class="py-3 px-3">
                <div class="text-slate-800 font-semibold">{dept}</div>
                <div class="text-[11px] text-slate-400">{desig}</div>
            </td>
            <td class="py-3 px-3">
                {badge_html}
            </td>
            <td class="py-3 px-4 text-right">
                <form action="/company/assign-role" method="POST" hx-post="/company/assign-role" hx-target="#role-row-{target_employee.id}" hx-swap="outerHTML" class="inline-flex items-center justify-end">
                    <input type="hidden" name="employee_id" value="{target_employee.id}">
                    <select name="role" onchange="this.form.requestSubmit()" class="text-xs font-bold bg-white border border-slate-300 hover:border-slate-400 rounded-lg px-3 py-1.5 text-slate-800 focus:outline-none focus:border-teal-600 shadow-2xs cursor-pointer">
                        {options_html}
                    </select>
                </form>
            </td>
        </tr>
        '''
        return HTMLResponse(row_html)

    return RedirectResponse(
        url=f"/company/profile?tab=permissions&success={quote_plus(f'Role for {target_employee.name} updated to {role_clean}')}",
        status_code=302
    )
