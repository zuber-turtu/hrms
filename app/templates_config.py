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
    Formats employee ID.
    If company.employee_id_prefix is set (e.g. 'TURTU'), returns 'TURTU-0001'.
    If prefix is not set or empty, returns original format '#0001'.
    """
    if emp_or_id is None or isinstance(emp_or_id, Undefined):
        return ""
    
    emp_id = None
    if hasattr(emp_or_id, "id") and not isinstance(emp_or_id, Undefined):
        try:
            emp_id = int(emp_or_id.id)
        except (ValueError, TypeError):
            pass
    if emp_id is None:
        try:
            emp_id = int(emp_or_id)
        except (ValueError, TypeError):
            return ""

    prefix = None
    if isinstance(company_or_prefix, str):
        prefix = company_or_prefix.strip() if company_or_prefix.strip() else None
    elif company_or_prefix is not None and not isinstance(company_or_prefix, Undefined):
        try:
            if hasattr(company_or_prefix, "employee_id_prefix") and company_or_prefix.employee_id_prefix:
                prefix = str(company_or_prefix.employee_id_prefix).strip()
        except Exception:
            pass

    if prefix is None and (company_or_prefix is None or isinstance(company_or_prefix, Undefined)):
        try:
            comp = get_global_company()
            if comp and comp.employee_id_prefix:
                prefix = comp.employee_id_prefix.strip()
        except Exception:
            pass
            
    if prefix:
        return f"{prefix.upper()}-{emp_id:04d}"
    return f"#{emp_id:04d}"


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
