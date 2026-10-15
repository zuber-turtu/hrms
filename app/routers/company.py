import json
import html
import httpx
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus

from app.database import get_db
from app.models.employee import Employee
from app.models.company import Company, OfficeLocation, CompanyZone
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.templates_config import templates
from app.utils.permissions import (
    AVAILABLE_PERMISSIONS,
    get_company_permissions,
    has_role_permission,
    can_manage_employee,
    can_assign_role,
    assert_can_manage_employee,
    assert_can_assign_role,
    get_role_rank,
)
from app.utils.geofence import get_active_office_locations, get_or_create_company

router = APIRouter(prefix="/company")

allow_hr_admin = RoleChecker(["super_admin", "admin", "hr", "hr_admin"])
allow_admin_only = RoleChecker(["super_admin", "admin"])

def require_company_settings_access(
    current_user: Employee = Depends(require_auth),
    db: Session = Depends(get_db),
) -> Employee:
    if current_user.role in ["super_admin", "admin", "hr", "hr_admin"] or getattr(current_user, "is_super_admin", False):
        return current_user
    company = db.query(Company).first()
    if has_role_permission(company, current_user.role, "company_settings"):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Operation not permitted: You do not have permission to view or manage company settings."
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/profile", response_class=HTMLResponse)
@router.get("/settings", response_class=HTMLResponse)
async def company_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_company_settings_access),
):
    company = get_or_create_company(db)

    employees = (
        db.query(Employee)
        .order_by(Employee.name.asc())
        .all()
    )

    permissions_matrix = get_company_permissions(company)
    locations = get_active_office_locations(db, company)
    
    # Fetch operating zones and employee counts per zone
    zones = db.query(CompanyZone).order_by(CompanyZone.id.asc()).all()
    zone_counts = {z.id: db.query(Employee).filter(Employee.zone_id == z.id).count() for z in zones}

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
            "locations": locations,
            "zones": zones,
            "zone_counts": zone_counts,
            "available_permissions": AVAILABLE_PERMISSIONS,
            "permissions_matrix": permissions_matrix,
        }
    )


@router.post("", response_class=HTMLResponse)
@router.post("/", response_class=HTMLResponse)
@router.post("/profile")
@router.post("/settings")
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
    current_user: Employee = Depends(allow_admin_only),
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
            company.employee_id_prefix = p_val.upper() if p_val else "TU"
        elif employee_id_prefix is not None:
            company.employee_id_prefix = employee_id_prefix.strip().upper() if employee_id_prefix.strip() else "TU"

        if "employee_id_separator" in form_data:
            sep = form_data["employee_id_separator"].strip()
            if sep == "custom" and "custom_separator" in form_data and form_data["custom_separator"].strip():
                sep = form_data["custom_separator"].strip()
            company.employee_id_separator = sep if sep else "-"

        if "employee_id_include_year" in form_data:
            company.employee_id_include_year = form_data.get("employee_id_include_year") in ["1", "true", "on", True]
        elif "section" in form_data and (form_data["section"] == "branding" or form_data["section"] == "employee_id"):
            # When unchecked in form submission
            company.employee_id_include_year = "employee_id_include_year" in form_data

        if "employee_id_include_dept" in form_data:
            company.employee_id_include_dept = form_data.get("employee_id_include_dept") in ["1", "true", "on", True]
        elif "section" in form_data and (form_data["section"] == "branding" or form_data["section"] == "employee_id"):
            company.employee_id_include_dept = "employee_id_include_dept" in form_data

        if "employee_id_padding" in form_data:
            try:
                company.employee_id_padding = max(1, min(8, int(form_data["employee_id_padding"])))
            except (ValueError, TypeError):
                company.employee_id_padding = 3

        if section == "branding":
            msg = "Corporate branding, ID pattern & identity updated successfully"
        elif section == "employee_id":
            msg = "Employee ID generation pattern updated successfully"

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
        
        for role in ["admin", "hr", "hr_admin", "manager", "employee", "intern"]:
            if role not in current_matrix:
                current_matrix[role] = {}
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
    valid_roles = ["super_admin", "admin", "hr", "hr_admin", "manager", "employee", "intern"]
    role_clean = role.strip().lower()
    if role_clean not in valid_roles:
        raise HTTPException(status_code=400, detail="Invalid system role")

    target_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not target_employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if current_user.id == target_employee.id:
        raise HTTPException(status_code=403, detail="Operation not permitted: You cannot change your own role.")

    # Hierarchical Privilege Enforcement:
    # 1. Lower role cannot modify/change role of equal or higher role
    # 2. Lower role cannot assign/promote anyone to equal or higher role
    assert_can_manage_employee(current_user, target_employee, "change the role of")
    assert_can_assign_role(current_user, role_clean)

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
            "super_admin": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-purple-100 text-purple-900 border border-purple-300">👑 Super Admin</span>',
            "admin": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">🛡️ Admin</span>',
            "hr_admin": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">📋 HR Admin</span>',
            "hr": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-teal-50 text-teal-700 border border-teal-200">📋 HR</span>',
            "manager": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">👔 Manager</span>',
            "intern": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">🌱 Intern</span>',
            "employee": '<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">💼 Employee</span>',
        }
        badge_html = role_badges.get(role_clean, role_badges["employee"])
        initials = (target_employee.name[:2] if target_employee.name else "EM").upper()
        dept = target_employee.department.name if hasattr(target_employee.department, "name") else (str(target_employee.department) if target_employee.department else "Unassigned")
        desig = target_employee.designation.name if hasattr(target_employee.designation, "name") else (str(target_employee.designation) if target_employee.designation else "Staff")
        
        system_roles = [
            ("intern", "Intern"),
            ("employee", "Employee"),
            ("manager", "Manager"),
            ("hr", "HR"),
            ("hr_admin", "HR Admin"),
            ("admin", "Admin"),
            ("super_admin", "Super Admin"),
        ]
        all_opts = [
            (r_val, r_label) for r_val, r_label in system_roles
            if can_assign_role(current_user, r_val) or r_val == role_clean
        ]

        options = []
        for r_val, r_label in all_opts:
            selected = "selected" if r_val == role_clean else ""
            options.append(f'<option value="{r_val}" {selected}>{r_label}</option>')
        options_html = "\n".join(options)

        company = db.query(Company).first()
        prefix = company.employee_id_prefix.strip() if (company and company.employee_id_prefix) else ""
        emp_code = f"{prefix.upper()}-{target_employee.id:04d}" if prefix else f"#{target_employee.id:04d}"

        safe_name = html.escape(str(target_employee.name or ""))
        safe_email = html.escape(str(target_employee.email or ""))
        safe_dept = html.escape(str(dept or ""))
        safe_desig = html.escape(str(desig or ""))
        safe_emp_code = html.escape(str(emp_code or ""))
        safe_initials = html.escape(str(initials or ""))
        safe_role_clean = html.escape(str(role_clean or ""))

        row_html = f'''
        <tr class="hover:bg-slate-50/60 transition-colors role-assign-row bg-emerald-50/40" id="role-row-{target_employee.id}" data-name="{safe_name.lower()}" data-dept="{safe_dept.lower()}" data-role="{safe_role_clean}" data-email="{safe_email.lower()}">
            <td class="py-3 px-4">
                <div class="flex items-center space-x-2.5">
                    <div class="w-8 h-8 rounded-full bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-xs border border-slate-200 shrink-0">
                        {safe_initials}
                    </div>
                    <div>
                        <div class="font-bold text-slate-900 flex items-center space-x-1.5">
                            <span>{safe_name}</span>
                            <span class="inline-flex items-center text-[10px] font-semibold text-emerald-700 bg-emerald-100/80 px-1.5 py-0.5 rounded animate-pulse">✓ Updated</span>
                        </div>
                        <div class="text-[11px] text-slate-400">{safe_email} &bull; <span class="font-mono text-slate-500">{safe_emp_code}</span></div>
                    </div>
                </div>
            </td>
            <td class="py-3 px-3">
                <div class="text-slate-800 font-semibold">{safe_dept}</div>
                <div class="text-[11px] text-slate-400">{safe_desig}</div>
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


# =========================================================================
# NAMED GEOFENCE LOCATIONS CRUD & OPENSTREETMAP ADDRESS SEARCH PROXY
# =========================================================================

@router.get("/locations/search-address", response_class=JSONResponse)
async def search_address(
    request: Request,
    q: Optional[str] = None,
    current_user: Employee = Depends(allow_hr_admin),
):
    """
    100% Free OpenStreetMap Nominatim Geocoding API Proxy.
    Returns parsed title, subtitle, display_name, latitude, and longitude.
    """
    if not q or len(q.strip()) < 2:
        return []

    query = q.strip()
    headers = {
        "User-Agent": "CompanyHRMS-App/1.0 (contact@Company.in; HRMS Geofencing)",
        "Accept-Language": "en",
    }
    params = {
        "q": query,
        "format": "json",
        "addressdetails": "1",
        "limit": "7",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers=headers,
            )
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            results = []
            for item in data:
                raw_name = item.get("display_name", "")
                parts = [p.strip() for p in raw_name.split(",") if p.strip()]
                title = parts[0] if parts else query
                subtitle = ", ".join(parts[1:5]) if len(parts) > 1 else raw_name

                results.append({
                    "title": title,
                    "subtitle": subtitle,
                    "display_name": raw_name,
                    "latitude": float(item["lat"]),
                    "longitude": float(item["lon"]),
                })
            return results
    except Exception as e:
        print(f"[OSM Search Error]: {e}")
        return []


@router.post("/locations/create")
async def create_office_location(
    request: Request,
    name: str = Form(...),
    code: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    latitude: float = Form(...),
    longitude: float = Form(...),
    radius_meters: int = Form(200),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Location name is required")

    company = get_or_create_company(db)

    # If this is marked primary, unset other primaries
    if is_primary:
        db.query(OfficeLocation).update({OfficeLocation.is_primary: False})
        company.office_latitude = latitude
        company.office_longitude = longitude
        company.geofence_radius_meters = radius_meters

    # Check if this is the very first location created
    existing_count = db.query(OfficeLocation).count()
    if existing_count == 0:
        is_primary = True
        company.office_latitude = latitude
        company.office_longitude = longitude
        company.geofence_radius_meters = radius_meters

    loc = OfficeLocation(
        name=clean_name,
        code=code.strip().upper() if code and code.strip() else None,
        address=address.strip() if address and address.strip() else None,
        latitude=latitude,
        longitude=longitude,
        radius_meters=max(10, radius_meters),
        is_primary=is_primary,
        is_active=True,
    )
    db.add(loc)
    db.commit()

    # Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_GEOFENCE_LOCATION",
        entity="OfficeLocation",
        entity_id=loc.id,
        new_value=f"{loc.name} ({loc.latitude}, {loc.longitude} • {loc.radius_meters}m)",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=geofence&success={quote_plus(f'Geofence location «{loc.name}» created successfully')}",
        status_code=302,
    )


@router.post("/locations/{loc_id}/edit")
async def edit_office_location(
    loc_id: int,
    request: Request,
    name: str = Form(...),
    code: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    latitude: float = Form(...),
    longitude: float = Form(...),
    radius_meters: int = Form(200),
    is_primary: bool = Form(False),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    loc = db.query(OfficeLocation).filter(OfficeLocation.id == loc_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    company = get_or_create_company(db)

    if is_primary:
        db.query(OfficeLocation).filter(OfficeLocation.id != loc_id).update({OfficeLocation.is_primary: False})
        company.office_latitude = latitude
        company.office_longitude = longitude
        company.geofence_radius_meters = radius_meters

    loc.name = name.strip()
    loc.code = code.strip().upper() if code and code.strip() else None
    loc.address = address.strip() if address and address.strip() else None
    loc.latitude = latitude
    loc.longitude = longitude
    loc.radius_meters = max(10, radius_meters)
    loc.is_primary = is_primary
    loc.is_active = is_active

    db.commit()

    # Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="EDIT_GEOFENCE_LOCATION",
        entity="OfficeLocation",
        entity_id=loc.id,
        new_value=f"{loc.name} ({loc.latitude}, {loc.longitude} • {loc.radius_meters}m)",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=geofence&success={quote_plus(f'Location «{loc.name}» updated successfully')}",
        status_code=302,
    )


@router.post("/locations/{loc_id}/delete")
async def delete_office_location(
    loc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    loc = db.query(OfficeLocation).filter(OfficeLocation.id == loc_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    loc_name = loc.name
    was_primary = loc.is_primary

    db.delete(loc)
    db.commit()

    # If primary was deleted, elect another location as primary if available
    if was_primary:
        next_loc = db.query(OfficeLocation).filter(OfficeLocation.is_active == True).first()
        if next_loc:
            next_loc.is_primary = True
            company = get_or_create_company(db)
            company.office_latitude = next_loc.latitude
            company.office_longitude = next_loc.longitude
            company.geofence_radius_meters = next_loc.radius_meters
            db.commit()

    # Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="DELETE_GEOFENCE_LOCATION",
        entity="OfficeLocation",
        entity_id=loc_id,
        old_value=loc_name,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=geofence&success={quote_plus(f'Location «{loc_name}» deleted successfully')}",
        status_code=302,
    )


@router.post("/locations/{loc_id}/set-primary")
async def set_primary_location(
    loc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    loc = db.query(OfficeLocation).filter(OfficeLocation.id == loc_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    db.query(OfficeLocation).update({OfficeLocation.is_primary: False})
    loc.is_primary = True

    company = get_or_create_company(db)
    company.office_latitude = loc.latitude
    company.office_longitude = loc.longitude
    company.geofence_radius_meters = loc.radius_meters

    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=geofence&success={quote_plus(f'«{loc.name}» set as primary office headquarters')}",
        status_code=302,
    )


# =====================================================================
# OPERATING ZONES MANAGEMENT ENDPOINTS
# =====================================================================

@router.post("/zones/create")
async def create_company_zone(
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    clean_name = name.strip()
    clean_code = code.strip().upper()
    clean_desc = description.strip() if description and description.strip() else None

    # Check uniqueness of name and code
    existing_name = db.query(CompanyZone).filter(CompanyZone.name.ilike(clean_name)).first()
    if existing_name:
        return RedirectResponse(
            url=f"/company/profile?tab=zones&error={quote_plus(f'An operating zone named «{clean_name}» already exists.')}",
            status_code=302,
        )

    existing_code = db.query(CompanyZone).filter(CompanyZone.code.ilike(clean_code)).first()
    if existing_code:
        return RedirectResponse(
            url=f"/company/profile?tab=zones&error={quote_plus(f'An operating zone with code «{clean_code}» already exists.')}",
            status_code=302,
        )

    zone = CompanyZone(
        name=clean_name,
        code=clean_code,
        description=clean_desc,
        is_active=True,
    )
    db.add(zone)
    db.commit()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_COMPANY_ZONE",
        entity="CompanyZone",
        entity_id=zone.id,
        new_value=f"{zone.name} ({zone.code})",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=zones&success={quote_plus(f'Operating Zone «{zone.name}» ({zone.code}) created successfully')}",
        status_code=302,
    )


@router.post("/zones/{zone_id}/edit")
async def edit_company_zone(
    zone_id: int,
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    description: Optional[str] = Form(None),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    zone = db.query(CompanyZone).filter(CompanyZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    clean_name = name.strip()
    clean_code = code.strip().upper()
    clean_desc = description.strip() if description and description.strip() else None

    existing_name = db.query(CompanyZone).filter(CompanyZone.name.ilike(clean_name), CompanyZone.id != zone_id).first()
    if existing_name:
        return RedirectResponse(
            url=f"/company/profile?tab=zones&error={quote_plus(f'An operating zone named «{clean_name}» already exists.')}",
            status_code=302,
        )

    existing_code = db.query(CompanyZone).filter(CompanyZone.code.ilike(clean_code), CompanyZone.id != zone_id).first()
    if existing_code:
        return RedirectResponse(
            url=f"/company/profile?tab=zones&error={quote_plus(f'An operating zone with code «{clean_code}» already exists.')}",
            status_code=302,
        )

    zone.name = clean_name
    zone.code = clean_code
    zone.description = clean_desc
    zone.is_active = is_active
    db.commit()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="EDIT_COMPANY_ZONE",
        entity="CompanyZone",
        entity_id=zone.id,
        new_value=f"{zone.name} ({zone.code}) - Active: {zone.is_active}",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=zones&success={quote_plus(f'Operating Zone «{zone.name}» updated successfully')}",
        status_code=302,
    )


@router.post("/zones/{zone_id}/toggle-status")
async def toggle_company_zone_status(
    zone_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    zone = db.query(CompanyZone).filter(CompanyZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    zone.is_active = not zone.is_active
    db.commit()

    status_str = "activated" if zone.is_active else "deactivated"
    return RedirectResponse(
        url=f"/company/profile?tab=zones&success={quote_plus(f'Zone «{zone.name}» has been {status_str}')}",
        status_code=302,
    )


@router.post("/zones/{zone_id}/delete")
async def delete_company_zone(
    zone_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_admin_only),
):
    zone = db.query(CompanyZone).filter(CompanyZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    assigned_emp_count = db.query(Employee).filter(Employee.zone_id == zone_id).count()
    if assigned_emp_count > 0:
        return RedirectResponse(
            url=f"/company/profile?tab=zones&error={quote_plus(f'Cannot delete «{zone.name}» because {assigned_emp_count} employee(s) are assigned to it. Please reassign them first.')}",
            status_code=302,
        )

    zone_name = zone.name
    db.delete(zone)
    db.commit()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="DELETE_COMPANY_ZONE",
        entity="CompanyZone",
        entity_id=zone_id,
        old_value=zone_name,
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(
        url=f"/company/profile?tab=zones&success={quote_plus(f'Operating Zone «{zone_name}» has been deleted successfully')}",
        status_code=302,
    )


