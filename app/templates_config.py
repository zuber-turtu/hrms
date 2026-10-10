from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app.models.company import Company
from app.config import settings
from app.utils.timezone import get_ist_today

def get_global_company() -> Company:
    """Returns the primary company record or creates one with defaults."""
    db = SessionLocal()
    try:
        company = db.query(Company).first()
        if not company:
            from app.utils.geofence import get_or_create_company
            company = get_or_create_company(db)
        return company
    except Exception:
        # Return a fallback Company model instance if DB is momentarily unreachable
        return Company(
            name=settings.COMPANY_NAME,
            tagline=settings.COMPANY_TAGLINE,
            address=settings.COMPANY_ADDRESS,
            currency_symbol=settings.COMPANY_CURRENCY_SYMBOL,
            currency_code=settings.COMPANY_CURRENCY_CODE,
            working_days_per_month=settings.COMPANY_WORKING_DAYS_PER_MONTH,
            standard_hours_per_day=settings.COMPANY_STANDARD_HOURS_PER_DAY,
            half_day_threshold_hours=settings.COMPANY_HALF_DAY_HOURS,
            lunch_break_hours=settings.COMPANY_LUNCH_BREAK_HOURS,
            lunch_start_time=settings.COMPANY_LUNCH_START_TIME,
            lunch_end_time=settings.COMPANY_LUNCH_END_TIME,
        )
    finally:
        db.close()


from jinja2.runtime import Undefined

def format_emp_code(emp_or_id, company_or_prefix=None) -> str:
    """
    Formats employee ID dynamically based on Company Settings & Department Code:
    Pattern: {PREFIX}{SEPARATOR}{YEAR}{SEPARATOR}{DEPT_CODE}{SEPARATOR}{SEQUENCE}
    Example: TU-2012-EX-001 or TU/2012/EX/001 or TU.2012.EX.001
    """
    if emp_or_id is None or isinstance(emp_or_id, Undefined):
        return ""
    
    emp_id = None
    emp_obj = None
    if hasattr(emp_or_id, "id") and not isinstance(emp_or_id, Undefined):
        try:
            emp_id = int(emp_or_id.id)
            emp_obj = emp_or_id
        except (ValueError, TypeError):
            pass
    if emp_id is None:
        try:
            emp_id = int(emp_or_id)
        except (ValueError, TypeError):
            return ""

    # Resolve company settings
    company = None
    if company_or_prefix is not None and not isinstance(company_or_prefix, (str, Undefined)):
        company = company_or_prefix
    
    if company is None or not hasattr(company, "employee_id_prefix"):
        try:
            company = get_global_company()
        except Exception:
            company = None

    # Determine format parameters
    prefix = "TU"
    separator = "-"
    include_year = True
    include_dept = True
    padding = 3

    if isinstance(company_or_prefix, str) and company_or_prefix.strip():
        prefix = company_or_prefix.strip()
    elif company:
        if company.employee_id_prefix:
            prefix = str(company.employee_id_prefix).strip()
        if hasattr(company, "employee_id_separator") and company.employee_id_separator is not None:
            separator = str(company.employee_id_separator)
        if hasattr(company, "employee_id_include_year") and company.employee_id_include_year is not None:
            include_year = bool(company.employee_id_include_year)
        if hasattr(company, "employee_id_include_dept") and company.employee_id_include_dept is not None:
            include_dept = bool(company.employee_id_include_dept)
        if hasattr(company, "employee_id_padding") and company.employee_id_padding:
            try:
                padding = max(1, min(8, int(company.employee_id_padding)))
            except (ValueError, TypeError):
                padding = 3

    # Extract Year
    year_str = None
    if include_year:
        if emp_obj and hasattr(emp_obj, "joining_date") and emp_obj.joining_date:
            try:
                year_str = str(emp_obj.joining_date.year)
            except Exception:
                year_str = str(get_ist_today().year)
        else:
            year_str = str(get_ist_today().year)

    # Extract Department Code
    dept_code = None
    if include_dept:
        if emp_obj and hasattr(emp_obj, "department") and emp_obj.department:
            dept = emp_obj.department
            if hasattr(dept, "code") and dept.code:
                dept_code = str(dept.code).strip().upper()
            elif hasattr(dept, "name") and dept.name:
                dept_code = str(dept.name).strip()[:3].upper()
            elif isinstance(dept, str) and dept.strip():
                dept_code = dept.strip()[:3].upper()
        if not dept_code:
            dept_code = "GEN"

    # Format Sequence Number with zero padding
    seq_str = f"{emp_id:0{padding}d}"

    # Build segments
    segments = []
    if prefix:
        segments.append(prefix.upper())
    if year_str:
        segments.append(year_str)
    if dept_code:
        segments.append(dept_code)
    segments.append(seq_str)

    return separator.join(segments)


from app.utils.flash import extract_flash_messages

templates = Jinja2Templates(directory="app/templates")

# Register Global Helpers across all Jinja templates
templates.env.globals["get_company"] = get_global_company
templates.env.globals["app_settings"] = settings
templates.env.globals["app_year"] = settings.APP_COPYRIGHT_YEAR or get_ist_today().year
templates.env.globals["get_today"] = get_ist_today
templates.env.globals["format_emp_code"] = format_emp_code
templates.env.globals["get_flash_messages"] = extract_flash_messages
templates.env.filters["format_emp_code"] = format_emp_code
