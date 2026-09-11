from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class AttendanceStatusOut(BaseModel):
    is_checked_in: bool
    active_check_in: Optional[datetime] = None
    last_check_out: Optional[datetime] = None
    accumulated_seconds: int = 0
    accumulated_time_str: str = "00:00:00"


class AttendanceCheckInRequest(BaseModel):
    notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AttendanceLogItem(BaseModel):
    id: int
    date: date
    employee_id: int
    employee_name: str
    employee_role: str
    department_name: Optional[str] = None
    sessions: str
    total_active: str
    is_missed: bool
    is_overridden: bool
    override_reason: Optional[str] = None
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None

    class Config:
        from_attributes = True


class AttendanceOverrideRequest(BaseModel):
    check_in_time: Optional[str] = None  # Format "HH:MM"
    check_out_time: Optional[str] = None # Format "HH:MM"
    reason: str = "Manual HR Adjustment"
