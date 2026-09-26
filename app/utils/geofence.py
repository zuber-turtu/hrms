import math
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.company import Company
from app.models.employee import Employee
from app.config import settings


def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes geographical distance between two (latitude, longitude) coordinates
    using the Haversine formula on a spherical Earth (radius = 6,371,000 meters).
    """
    R = 6371000.0  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def get_or_create_company(db: Session) -> Company:
    """
    Returns the primary company record or creates one with defaults.
    """
    company = db.query(Company).first()
    if not company:
        company = Company(
            name="TURTU",
            address="Belagavi, Karnataka",
            office_latitude=settings.GEOFENCE_DEFAULT_LAT,
            office_longitude=settings.GEOFENCE_DEFAULT_LON,
            geofence_radius_meters=settings.GEOFENCE_DEFAULT_RADIUS_METERS,
            geofence_enabled=settings.GEOFENCE_ENABLED,
            geofence_strict_mode=settings.GEOFENCE_STRICT_MODE,
        )
        db.add(company)
        db.commit()
        db.refresh(company)
    return company


def validate_punch_geofence(
    db: Session,
    employee: Employee,
    lat: Optional[float],
    lon: Optional[float],
) -> Tuple[bool, Optional[str], Optional[float], bool, Company]:
    """
    Validates whether an employee punch is allowed based on company geofencing rules.
    
    Returns:
        (is_allowed, message, distance_meters, is_exempt, company)
    """
    company = get_or_create_company(db)

    # 1. If geofencing is globally disabled
    if not company.geofence_enabled or not settings.GEOFENCE_ENABLED:
        return True, None, None, False, company

    # 2. Check employee exemption (e.g. Remote / Field / WFH approved staff)
    is_exempt = bool(employee.profile and employee.profile.is_geofence_exempt)
    
    office_lat = company.office_latitude if company.office_latitude is not None else settings.GEOFENCE_DEFAULT_LAT
    office_lon = company.office_longitude if company.office_longitude is not None else settings.GEOFENCE_DEFAULT_LON

    # If employee is exempt, calculate distance if coords provided, and always allow
    if is_exempt:
        dist = None
        if lat is not None and lon is not None and office_lat is not None and office_lon is not None:
            try:
                dist = calculate_distance_meters(office_lat, office_lon, lat, lon)
            except Exception:
                dist = None
        return True, None, dist, True, company

    # 3. If office coordinates are not configured in system, allow with warning
    if office_lat is None or office_lon is None:
        return True, None, None, False, company

    # 4. Check if punch coordinates are provided
    if lat is None or lon is None:
        if company.geofence_strict_mode:
            return False, "GPS location is required to verify office presence. Please enable device location.", None, False, company
        return True, "No GPS location provided", None, False, company

    # 5. Compute distance via Haversine
    try:
        dist_m = calculate_distance_meters(office_lat, office_lon, lat, lon)
    except Exception as e:
        if company.geofence_strict_mode:
            return False, f"Invalid GPS coordinates provided: {e}", None, False, company
        return True, "Coordinates error", None, False, company

    allowed_radius = company.geofence_radius_meters or settings.GEOFENCE_DEFAULT_RADIUS_METERS

    # 6. Check perimeter range
    if dist_m <= allowed_radius:
        return True, None, dist_m, False, company

    # Outside perimeter
    if company.geofence_strict_mode:
        err = f"Punch rejected: You are {int(dist_m)}m away from office (allowed perimeter: {allowed_radius}m)."
        return False, err, dist_m, False, company
    else:
        warn = f"Recorded outside perimeter ({int(dist_m)}m)"
        return True, warn, dist_m, False, company
