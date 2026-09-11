from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class ProfileBase(BaseModel):
    phone_number: Optional[str] = None
    gender: Optional[str] = None
    home_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    qualification: Optional[str] = None
    experience: Optional[str] = None
    aadhar_number: Optional[str] = None
    pan_number: Optional[str] = None


class ProfileOut(ProfileBase):
    id: int
    employee_id: int

    class Config:
        from_attributes = True


class BankAccountOut(BaseModel):
    id: int
    employee_id: int
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

    class Config:
        from_attributes = True


class EmergencyContactOut(BaseModel):
    id: int
    employee_id: int
    contact_name: Optional[str] = None
    relationship: Optional[str] = None
    phone_number: Optional[str] = None

    class Config:
        from_attributes = True


class SalaryStructureBase(BaseModel):
    base_salary: float = 0.0
    hra: float = 0.0
    custom_allowances: float = 0.0
    pf_deduction: float = 0.0
    tax_deduction: float = 0.0


class SalaryStructureOut(SalaryStructureBase):
    id: int
    employee_id: int
    effective_date: Optional[date] = None

    class Config:
        from_attributes = True


class EmployeeCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Optional[str] = "employee"
    department_id: Optional[int] = None
    designation_id: Optional[int] = None
    department_name: Optional[str] = None
    designation_title: Optional[str] = None
    joining_date: Optional[date] = None
    
    # Profile fields (flat or nested)
    phone_number: Optional[str] = None
    phone: Optional[str] = None # alias
    gender: Optional[str] = None
    home_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    qualification: Optional[str] = None
    experience: Optional[str] = None
    aadhar_number: Optional[str] = None
    pan_number: Optional[str] = None

    # Bank fields
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

    # Emergency Contact fields
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None

    # Salary fields
    base_salary: Optional[float] = 0.0
    hra: Optional[float] = 0.0
    custom_allowances: Optional[float] = 0.0
    pf_deduction: Optional[float] = 0.0
    tax_deduction: Optional[float] = 0.0

    profile: Optional[ProfileBase] = None
    salary: Optional[SalaryStructureBase] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    department_id: Optional[int] = None
    designation_id: Optional[int] = None
    department_name: Optional[str] = None
    designation_title: Optional[str] = None
    joining_date: Optional[date] = None
    is_active: Optional[bool] = None

    # Profile fields
    phone_number: Optional[str] = None
    phone: Optional[str] = None # alias
    gender: Optional[str] = None
    home_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    qualification: Optional[str] = None
    experience: Optional[str] = None
    aadhar_number: Optional[str] = None
    pan_number: Optional[str] = None

    # Bank fields
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

    # Emergency Contact fields
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None

    # Salary fields
    base_salary: Optional[float] = None
    hra: Optional[float] = None
    custom_allowances: Optional[float] = None
    pf_deduction: Optional[float] = None
    tax_deduction: Optional[float] = None

    profile: Optional[ProfileBase] = None
    salary: Optional[SalaryStructureBase] = None


class EmployeeOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    department_id: Optional[int] = None
    designation_id: Optional[int] = None
    department_name: Optional[str] = None
    designation_title: Optional[str] = None
    joining_date: Optional[date] = None
    is_active: bool

    # Contact & Personal details
    phone_number: Optional[str] = None
    gender: Optional[str] = None
    home_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    qualification: Optional[str] = None
    experience: Optional[str] = None
    aadhar_number: Optional[str] = None
    pan_number: Optional[str] = None

    # Bank info
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_contact_relation: Optional[str] = None

    # Salary info
    base_salary: float = 0.0
    hra: float = 0.0
    custom_allowances: float = 0.0
    pf_deduction: float = 0.0
    tax_deduction: float = 0.0

    profile: Optional[ProfileOut] = None
    salary_structure: Optional[SalaryStructureOut] = None
    bank_account: Optional[BankAccountOut] = None

    class Config:
        from_attributes = True


class AdminPasswordReset(BaseModel):
    new_password: str
