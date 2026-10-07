import math
import datetime
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from app.models.company import Company, OfficeLocation
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
    Returns the primary company record or creates one with dynamic configuration defaults.
    """
    company = db.query(Company).first()
    if not company:
        company = Company(
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


def get_active_office_locations(db: Session, company: Optional[Company] = None) -> List[OfficeLocation]:
    """
    Returns all active named office geofence locations.
    If none exist, automatically seeds a primary location from company defaults.
    """
    locations = (
        db.query(OfficeLocation)
        .filter(OfficeLocation.is_active == True)
        .order_by(OfficeLocation.is_primary.desc(), OfficeLocation.id.asc())
        .all()
    )
    if not locations:
        if not company:
            company = get_or_create_company(db)
        office_lat = company.office_latitude if company.office_latitude is not None else settings.GEOFENCE_DEFAULT_LAT
        office_lon = company.office_longitude if company.office_longitude is not None else settings.GEOFENCE_DEFAULT_LON
        if office_lat is not None and office_lon is not None:
            default_loc = OfficeLocation(
                name=f"{company.name or 'Main'} Office",
                code="HQ-01",
                address=company.address or "Main Headquarters",
                latitude=office_lat,
                longitude=office_lon,
                radius_meters=company.geofence_radius_meters or settings.GEOFENCE_DEFAULT_RADIUS_METERS,
                is_primary=True,
                is_active=True,
            )
            db.add(default_loc)
            db.commit()
            db.refresh(default_loc)
            return [default_loc]
    return locations


def get_active_wfh_request(db: Session, employee_id: int, target_date: Optional[datetime.date] = None):
    """
    Checks if the employee has an approved Work From Home (WFH) allocation on the target date.
    """
    from app.models.leave import WfhRequest
    from app.utils.timezone import get_ist_today
    
    check_date = target_date or get_ist_today()
    return (
        db.query(WfhRequest)
        .filter(
            WfhRequest.employee_id == employee_id,
            WfhRequest.status == "approved",
            WfhRequest.start_date <= check_date,
            WfhRequest.end_date >= check_date,
        )
        .first()
    )


class GeofenceValidationResult:
    """
    Encapsulates validation result with dual unpacking support for 5-tuple and 7-tuple callers.
    """
    def __init__(
        self,
        is_allowed: bool,
        message: Optional[str],
        distance_meters: Optional[float],
        is_exempt: bool,
        company: Company,
        location_name: Optional[str] = None,
        in_range: bool = True,
    ):
        self.is_allowed = is_allowed
        self.message = message
        self.distance_meters = distance_meters
        self.is_exempt = is_exempt
        self.company = company
        self.location_name = location_name
        self.in_range = in_range

    @property
    def distance_m(self) -> Optional[float]:
        return self.distance_meters

    def __iter__(self):
        yield self.is_allowed
        yield self.message
        yield self.distance_meters
        yield self.is_exempt
        yield self.company
        yield self.location_name
        yield self.in_range

    def __getitem__(self, idx):
        items = [
            self.is_allowed,
            self.message,
            self.distance_meters,
            self.is_exempt,
            self.company,
            self.location_name,
            self.in_range,
        ]
        return items[idx]


def validate_punch_geofence(
    db: Session,
    employee: Employee,
    lat: Optional[float],
    lon: Optional[float],
    punch_date: Optional[datetime.date] = None,
) -> GeofenceValidationResult:
    """
    Validates whether an employee punch is allowed based on multi-perimeter office geofencing rules and WFH approvals.
    """
    company = get_or_create_company(db)

    # 1. If geofencing is globally disabled on the company profile
    if not company.geofence_enabled:
        return GeofenceValidationResult(True, None, None, False, company, "Office (Geofence Disabled)", True)

    # 2. Check if employee has an approved Work From Home (WFH) allocation for today
    wfh_req = get_active_wfh_request(db, employee.id, punch_date)
    is_wfh_approved = wfh_req is not None

    # 3. Check employee profile exemption (e.g. Remote / Field staff) or active WFH
    is_profile_exempt = bool(employee.profile and employee.profile.is_geofence_exempt)
    is_exempt = is_profile_exempt or is_wfh_approved

    active_locations = get_active_office_locations(db, company)

    # If employee is exempt or on approved WFH, compute distance to nearest location if coords provided
    if is_exempt:
        dist = None
        nearest_loc_name = "Work From Home" if is_wfh_approved else "Remote Work"
        if lat is not None and lon is not None and active_locations:
            try:
                distances = [
                    (calculate_distance_meters(loc.latitude, loc.longitude, lat, lon), loc)
                    for loc in active_locations
                ]
                distances.sort(key=lambda x: x[0])
                dist, nearest_loc = distances[0]
                nearest_loc_name = f"{'WFH' if is_wfh_approved else 'Remote'} ({nearest_loc.name})"
            except Exception:
                dist = None
        msg = "🏠 Work From Home (Approved)" if is_wfh_approved else None
        return GeofenceValidationResult(True, msg, dist, True, company, nearest_loc_name, True)

    # 4. If no active office locations configured
    if not active_locations:
        return GeofenceValidationResult(True, None, None, False, company, "Unconfigured Location", True)

    # 5. Check if punch coordinates are provided
    if lat is None or lon is None:
        if company.geofence_strict_mode:
            return GeofenceValidationResult(
                False,
                "GPS location is required to verify office presence. Please enable device location.",
                None,
                False,
                company,
                None,
                False,
            )
        return GeofenceValidationResult(True, "No GPS location provided", None, False, company, "Unknown Location", True)

    # 6. Multi-Perimeter Calculation: Check against all active named office geofences
    location_distances = []
    matched_location = None
    matched_distance = None

    for loc in active_locations:
        try:
            d_m = calculate_distance_meters(loc.latitude, loc.longitude, lat, lon)
            allowed_r = loc.radius_meters or 200
            location_distances.append((d_m, loc, allowed_r))
            if d_m <= allowed_r and (matched_distance is None or d_m < matched_distance):
                matched_location = loc
                matched_distance = d_m
        except Exception:
            continue

    if not location_distances:
        if company.geofence_strict_mode:
            return GeofenceValidationResult(False, "Invalid GPS coordinates", None, False, company, None, False)
        return GeofenceValidationResult(True, "Coordinates error", None, False, company, "Unknown Location", True)

    # Sort to find nearest location
    location_distances.sort(key=lambda x: x[0])
    min_dist, nearest_loc, nearest_radius = location_distances[0]

    # 7. Check if inside ANY active office geofence perimeter
    if matched_location is not None:
        # Verified inside named office perimeter!
        return GeofenceValidationResult(
            True,
            None,
            matched_distance,
            False,
            company,
            matched_location.name,
            True,
        )

    # 8. Outside all configured office perimeters
    if company.geofence_strict_mode:
        err = f"Punch rejected: You are {int(min_dist)}m away from nearest office ({nearest_loc.name}). Allowed perimeter: {nearest_radius}m."
        return GeofenceValidationResult(
            False,
            err,
            min_dist,
            False,
            company,
            nearest_loc.name,
            False,
        )
    else:
        warn = f"Recorded outside perimeter ({int(min_dist)}m from {nearest_loc.name})"
        return GeofenceValidationResult(
            True,
            warn,
            min_dist,
            False,
            company,
            f"Outside {nearest_loc.name}",
            False,
        )
