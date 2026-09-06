from sqlalchemy import Column, Integer, String, Boolean, Date, Float, ForeignKey
from sqlalchemy.orm import relationship as orm_relationship
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
    joining_date = Column(Date, default=datetime.date.today)
    
    # Foreign Keys to Department & Designation (3NF Normalization)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    designation_id = Column(Integer, ForeignKey("designations.id"), nullable=True)
    
    # Auth & Security details
    reset_token = Column(String, nullable=True)

    # Relational Mappings
    department = orm_relationship("Department", back_populates="employees")
    designation = orm_relationship("Designation", back_populates="employees")
    profile = orm_relationship("EmployeeProfile", back_populates="employee", uselist=False, cascade="all, delete-orphan")
    bank_account = orm_relationship("EmployeeBankAccount", back_populates="employee", uselist=False, cascade="all, delete-orphan")
    emergency_contacts = orm_relationship("EmployeeEmergencyContact", back_populates="employee", cascade="all, delete-orphan")
    salary_structure = orm_relationship("SalaryStructure", back_populates="employee", uselist=False, cascade="all, delete-orphan")
    
    attendances = orm_relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")
    payslips = orm_relationship("Payslip", back_populates="employee", cascade="all, delete-orphan")

    # Backward compatibility properties for templates and helper access
    @property
    def phone_number(self):
        return self.profile.phone_number if self.profile else None

    @property
    def home_address(self):
        return self.profile.home_address if self.profile else None

    @property
    def city(self):
        return self.profile.city if self.profile else None

    @property
    def state(self):
        return self.profile.state if self.profile else None

    @property
    def country(self):
        return self.profile.country if self.profile else None

    @property
    def gender(self):
        return self.profile.gender if self.profile else None

    @property
    def qualification(self):
        return self.profile.qualification if self.profile else None

    @property
    def experience(self):
        return self.profile.experience if self.profile else None

    @property
    def aadhar_number(self):
        return self.profile.aadhar_number if self.profile else None

    @property
    def pan_number(self):
        return self.profile.pan_number if self.profile else None

    @property
    def bank_name(self):
        return self.bank_account.bank_name if self.bank_account else None

    @property
    def account_number(self):
        return self.bank_account.account_number if self.bank_account else None

    @property
    def ifsc_code(self):
        return self.bank_account.ifsc_code if self.bank_account else None

    @property
    def emergency_contact(self):
        if self.emergency_contacts and len(self.emergency_contacts) > 0:
            return self.emergency_contacts[0].phone_number
        return None

    @property
    def emergency_contact_name(self):
        if self.emergency_contacts and len(self.emergency_contacts) > 0:
            return self.emergency_contacts[0].contact_name
        return None

    @property
    def emergency_contact_relation(self):
        if self.emergency_contacts and len(self.emergency_contacts) > 0:
            return self.emergency_contacts[0].relationship
        return None

    @property
    def base_salary(self):
        return self.salary_structure.base_salary if self.salary_structure else 0.0

    @property
    def hra(self):
        return self.salary_structure.hra if self.salary_structure else 0.0

    @property
    def custom_allowances(self):
        return self.salary_structure.custom_allowances if self.salary_structure else 0.0

    @property
    def pf_deduction(self):
        return self.salary_structure.pf_deduction if self.salary_structure else 0.0

    @property
    def tax_deduction(self):
        return self.salary_structure.tax_deduction if self.salary_structure else 0.0


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), unique=True, index=True, nullable=False)
    
    phone_number = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    home_address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, nullable=True)
    qualification = Column(String, nullable=True)
    experience = Column(String, nullable=True)
    aadhar_number = Column(String, nullable=True)
    pan_number = Column(String, nullable=True)

    employee = orm_relationship("Employee", back_populates="profile")


class EmployeeBankAccount(Base):
    __tablename__ = "employee_bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), unique=True, index=True, nullable=False)
    
    bank_name = Column(String, nullable=True)
    account_number = Column(String, nullable=True)
    ifsc_code = Column(String, nullable=True)

    employee = orm_relationship("Employee", back_populates="bank_account")


class EmployeeEmergencyContact(Base):
    __tablename__ = "employee_emergency_contacts"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    
    contact_name = Column(String, nullable=True)
    relationship = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    is_primary = Column(Boolean, default=True)

    employee = orm_relationship("Employee", back_populates="emergency_contacts")


class SalaryStructure(Base):
    __tablename__ = "salary_structures"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), unique=True, index=True, nullable=False)
    
    base_salary = Column(Float, default=0.0)
    hra = Column(Float, default=0.0)
    custom_allowances = Column(Float, default=0.0)
    pf_deduction = Column(Float, default=0.0)
    tax_deduction = Column(Float, default=0.0)
    effective_date = Column(Date, default=datetime.date.today)

    employee = orm_relationship("Employee", back_populates="salary_structure")
