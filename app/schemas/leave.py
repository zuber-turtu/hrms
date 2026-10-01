from pydantic import BaseModel
from typing import Optional, List
import datetime


class LeaveTypeOut(BaseModel):
    id: int
    name: str
    code: str
    description: Optional[str] = None
    default_days_per_year: float
    is_paid: bool
    color_code: str
    is_active: bool

    class Config:
        from_attributes = True


class LeaveBalanceOut(BaseModel):
    id: int
    employee_id: int
    leave_type_id: int
    leave_type_name: str
    leave_type_code: str
    color_code: str
    is_paid: bool
    year: int
    total_allocated: float
    used_days: float
    pending_days: float
    remaining_days: float

    class Config:
        from_attributes = True


class LeaveApplicationCreate(BaseModel):
    leave_type_id: int
    start_date: datetime.date
    end_date: datetime.date
    is_half_day: bool = False
    half_day_session: Optional[str] = None  # 'first_half', 'second_half'
    reason: str


class LeaveApplicationOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    leave_type_id: int
    leave_type_name: Optional[str] = None
    leave_type_code: Optional[str] = None
    start_date: datetime.date
    end_date: datetime.date
    total_days: float
    is_half_day: bool
    half_day_session: Optional[str] = None
    reason: str
    status: str
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class LeaveReviewRequest(BaseModel):
    status: str  # 'approved' or 'rejected'
    rejection_reason: Optional[str] = None


class WfhRequestCreate(BaseModel):
    start_date: datetime.date
    end_date: datetime.date
    is_half_day: bool = False
    half_day_session: Optional[str] = None
    reason: str


class WfhDirectAllocateRequest(BaseModel):
    employee_id: int
    start_date: datetime.date
    end_date: datetime.date
    reason: str = "Direct WFH Allocation by Management"


class WfhRequestOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    start_date: datetime.date
    end_date: datetime.date
    total_days: float
    is_half_day: bool
    half_day_session: Optional[str] = None
    reason: str
    status: str
    is_direct_allocation: bool
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True
