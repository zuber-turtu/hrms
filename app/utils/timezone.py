import datetime
from typing import Optional

# Indian Standard Time (IST) is permanently UTC+05:30 with zero DST changes
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), name="IST")


def get_ist_now() -> datetime.datetime:
    """
    Returns the current date and time in Indian Standard Time (IST)
    as a naive datetime (for seamless compatibility with standard SQLite / Postgres DateTime fields).
    """
    return datetime.datetime.now(IST).replace(tzinfo=None)


def get_ist_now_aware() -> datetime.datetime:
    """
    Returns the current date and time in Indian Standard Time (IST)
    with timezone information (+05:30).
    """
    return datetime.datetime.now(IST)


def get_ist_today() -> datetime.date:
    """
    Returns the current calendar date in Indian Standard Time (IST).
    Prevents the 5.5 hour UTC rollover issue between 12:00 AM and 05:30 AM IST.
    """
    return get_ist_now().date()


def to_ist(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """
    Safely converts a datetime object (naive or aware) to naive IST datetime.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(IST).replace(tzinfo=None)
    return dt


def format_ist_time(dt: Optional[datetime.datetime], fmt: str = "%I:%M %p") -> str:
    """
    Formats a datetime into 12-hour AM/PM format in IST.
    """
    if dt is None:
        return ""
    ist_dt = to_ist(dt)
    return ist_dt.strftime(fmt)


def format_ist_datetime(dt: Optional[datetime.datetime], fmt: str = "%Y-%m-%d %I:%M:%S %p") -> str:
    """
    Formats a datetime into a standard date and time string in IST.
    """
    if dt is None:
        return ""
    ist_dt = to_ist(dt)
    return ist_dt.strftime(fmt)
