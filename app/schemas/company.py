from pydantic import BaseModel
from typing import Optional


class CompanyProfileBase(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    address: Optional[str] = None
    currency_symbol: Optional[str] = None
    currency_code: Optional[str] = None
    working_days_per_month: Optional[int] = None
    standard_hours_per_day: Optional[float] = None
    half_day_threshold_hours: Optional[float] = None
    lunch_break_hours: Optional[float] = 1.0
    lunch_start_time: Optional[str] = "13:00"
    lunch_end_time: Optional[str] = "14:00"
    support_email: Optional[str] = None
    website: Optional[str] = None
    cin: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    logo_url: Optional[str] = None
    signature_url: Optional[str] = None
    office_latitude: Optional[float] = None
    office_longitude: Optional[float] = None
    geofence_radius_meters: Optional[int] = 200
    geofence_enabled: Optional[bool] = False
    geofence_strict_mode: Optional[bool] = False


class CompanyProfileUpdate(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    address: Optional[str] = None
    currency_symbol: Optional[str] = None
    currency_code: Optional[str] = None
    working_days_per_month: Optional[int] = None
    standard_hours_per_day: Optional[float] = None
    half_day_threshold_hours: Optional[float] = None
    lunch_break_hours: Optional[float] = None
    lunch_start_time: Optional[str] = None
    lunch_end_time: Optional[str] = None
    support_email: Optional[str] = None
    website: Optional[str] = None
    cin: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    office_latitude: Optional[float] = None
    office_longitude: Optional[float] = None
    geofence_radius_meters: Optional[int] = None
    geofence_enabled: Optional[bool] = None
    geofence_strict_mode: Optional[bool] = None


class CompanyProfileOut(CompanyProfileBase):
    id: int

    class Config:
        from_attributes = True
