from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, Index
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.timezone import get_ist_today

class Payslip(Base):
    __tablename__ = "payslips"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    
    month = Column(Integer, index=True)  # 1 to 12
    year = Column(Integer, index=True)
    
    # Generated Dates
    generated_on = Column(Date, default=get_ist_today, index=True)
    
    # Actual paid days vs payable days
    payable_days = Column(Integer)
    days_worked = Column(Float)
    
    # Calculated / Edited components
    basic = Column(Float, default=0.0)
    hra = Column(Float, default=0.0)
    allowances = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)
    
    pf = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    other_deductions = Column(Float, default=0.0)
    
    net_salary = Column(Float, default=0.0)
    
    status = Column(String, default="draft", index=True)  # draft, finalized, paid

    employee = relationship("Employee", back_populates="payslips")

    __table_args__ = (
        Index("idx_payslip_emp_month_year", "employee_id", "month", "year"),
        Index("idx_payslip_period", "month", "year"),
    )

