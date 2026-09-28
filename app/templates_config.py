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
        )
    finally:
        db.close()


templates = Jinja2Templates(directory="app/templates")

# Register Global Helpers across all Jinja templates
templates.env.globals["get_company"] = get_global_company
templates.env.globals["app_settings"] = settings
templates.env.globals["app_year"] = settings.APP_COPYRIGHT_YEAR or get_ist_today().year
templates.env.globals["get_today"] = get_ist_today
