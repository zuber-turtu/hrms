from sqlalchemy import Column, Integer, String, Float, Boolean
from app.database import Base

class Company(Base):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    tagline = Column(String, nullable=True)
    address = Column(String, nullable=True)
    currency_symbol = Column(String, nullable=True)
    currency_code = Column(String, nullable=True)
    working_days_per_month = Column(Integer, nullable=True)
    standard_hours_per_day = Column(Float, nullable=True)
    half_day_threshold_hours = Column(Float, nullable=True)
    lunch_break_hours = Column(Float, default=1.0, nullable=True)
    lunch_start_time = Column(String, default="13:00", nullable=True)
    lunch_end_time = Column(String, default="14:00", nullable=True)
    support_email = Column(String, nullable=True)
    website = Column(String, nullable=True)

    # Branding Assets
    logo_url = Column(String, nullable=True)
    logo_file_id = Column(String, nullable=True)
    signature_url = Column(String, nullable=True)
    signature_file_id = Column(String, nullable=True)

    # Statutory & Tax Identification
    cin = Column(String, nullable=True)
    gstin = Column(String, nullable=True)
    pan = Column(String, nullable=True)

    # Geofencing & Office Location
    office_latitude = Column(Float, nullable=True)
    office_longitude = Column(Float, nullable=True)
    geofence_radius_meters = Column(Integer, default=200)
    geofence_enabled = Column(Boolean, default=False)
    geofence_strict_mode = Column(Boolean, default=False)

    # Dynamic Access Control & Role Permissions Matrix (JSON string)
    role_permissions = Column(String, nullable=True)

    # Employee ID Prefix (e.g. 'Company', 'EMP' -> Company-0001; if null/empty -> #0001)
    employee_id_prefix = Column(String, nullable=True)
