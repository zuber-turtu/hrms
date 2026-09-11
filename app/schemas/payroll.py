from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class GenerateDraftRequest(BaseModel):
    employee_id: int
    month: int
    year: int


class GenerateBulkDraftRequest(BaseModel):
    month: int
    year: int


class PayslipBase(BaseModel):
    basic: float = 0.0
    hra: float = 0.0
    allowances: float = 0.0
    bonus: float = 0.0
    pf: float = 0.0
    tax: float = 0.0
    other_deductions: float = 0.0
    payable_days: int = 22
    days_worked: float = 22.0
    status: str = "draft"


class PayslipUpdate(BaseModel):
    generated_on: Optional[date] = None
    payable_days: Optional[int] = None
    days_worked: Optional[float] = None
    basic: Optional[float] = None
    hra: Optional[float] = None
    allowances: Optional[float] = None
    bonus: Optional[float] = None
    pf: Optional[float] = None
    tax: Optional[float] = None
    other_deductions: Optional[float] = None
    net_salary: Optional[float] = None
    status: Optional[str] = None


class PayslipOut(PayslipBase):
    id: int
    employee_id: int
    month: int
    year: int
    generated_on: Optional[date] = None
    net_salary: float = 0.0
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    department_name: Optional[str] = None
    designation_title: Optional[str] = None

    class Config:
        from_attributes = True


class PayrollSummary(BaseModel):
    month: Optional[int] = None
    year: Optional[int] = None
    total_records: int
    total_net: float
    draft_count: int
    finalized_count: int
    payslips: List[PayslipOut] = []
