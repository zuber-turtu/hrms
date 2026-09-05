from sqlalchemy import Column, Integer, String, Boolean, Date, Float
from sqlalchemy.orm import relationship
from app.database import Base
import datetime

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Roles: admin, hr_admin, manager, employee
    role = Column(String, default="employee")
    is_active = Column(Boolean, default=True)
    
    name = Column(String, nullable=False)
    department = Column(String)
    designation = Column(String)
    joining_date = Column(Date, default=datetime.date.today)
    
    bank_name = Column(String)
    account_number = Column(String)
    ifsc_code = Column(String)
    
    # Base Salary details
    base_salary = Column(Float, default=0.0)
    hra = Column(Float, default=0.0)
    custom_allowances = Column(Float, default=0.0)
    pf_deduction = Column(Float, default=0.0)
    tax_deduction = Column(Float, default=0.0)

    # Rich Employee Profile Details
    phone_number = Column(String, nullable=True)
    home_address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    qualification = Column(String, nullable=True)
    experience = Column(String, nullable=True)
    emergency_contact = Column(String, nullable=True)
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_relation = Column(String, nullable=True)
    aadhar_number = Column(String, nullable=True)
    pan_number = Column(String, nullable=True)

    # Auth details
    reset_token = Column(String, nullable=True)

    attendances = relationship("Attendance", back_populates="employee")
    payslips = relationship("Payslip", back_populates="employee")

