from sqlalchemy import Column, Integer, String, Boolean, Date, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from app.utils.timezone import get_ist_now, get_ist_today


class LeaveType(Base):
    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)           # e.g., Casual Leave, Sick Leave
    code = Column(String(50), unique=True, index=True)   # e.g., CL, SL, EL, ML, LWP
    description = Column(Text, nullable=True)
    default_days_per_year = Column(Float, default=12.0)
    is_paid = Column(Boolean, default=True)              # Paid vs Unpaid (LWP)
    color_code = Column(String(50), default="#008080")   # Hex color for UI badges
    applicable_gender = Column(String(20), default="all") # 'all', 'female', 'male'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_ist_now)

    # Relationships
    applications = relationship("LeaveApplication", back_populates="leave_type")
    balances = relationship("LeaveBalance", back_populates="leave_type", cascade="all, delete-orphan")


class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False, index=True)
    year = Column(Integer, nullable=False, default=lambda: get_ist_today().year, index=True)
    
    total_allocated = Column(Float, default=12.0)        # Total quota for this year
    used_days = Column(Float, default=0.0)              # Approved leaves taken
    pending_days = Column(Float, default=0.0)           # Currently awaiting approval

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id])
    leave_type = relationship("LeaveType", back_populates="balances")

    @property
    def remaining_days(self) -> float:
        return max(0.0, self.total_allocated - self.used_days - self.pending_days)


class LeaveApplication(Base):
    __tablename__ = "leave_applications"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False, index=True)
    
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    total_days = Column(Float, nullable=False, default=1.0)
    
    is_half_day = Column(Boolean, default=False)
    half_day_session = Column(String(50), nullable=True) # 'first_half' or 'second_half'
    
    reason = Column(Text, nullable=False)
    document_url = Column(String(500), nullable=True)   # Optional medical cert or proof
    
    # Status: 'pending', 'approved', 'rejected', 'cancelled'
    status = Column(String(50), default="pending", index=True)
    
    reviewed_by_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=get_ist_now)

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id])
    reviewed_by = relationship("Employee", foreign_keys=[reviewed_by_id])
    leave_type = relationship("LeaveType", back_populates="applications")


class WfhRequest(Base):
    __tablename__ = "wfh_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    total_days = Column(Float, nullable=False, default=1.0)
    
    is_half_day = Column(Boolean, default=False)
    half_day_session = Column(String(50), nullable=True) # 'first_half' or 'second_half'
    
    reason = Column(Text, nullable=False)
    
    # Status: 'pending', 'approved', 'rejected', 'cancelled'
    status = Column(String(50), default="pending", index=True)
    
    reviewed_by_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    # True if directly allocated by admin/manager without employee request
    is_direct_allocation = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=get_ist_now)

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id])
    reviewed_by = relationship("Employee", foreign_keys=[reviewed_by_id])
