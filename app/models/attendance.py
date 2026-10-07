from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Boolean, Float, Index
from sqlalchemy.orm import relationship
from app.database import Base

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    check_in = Column(DateTime)
    check_out = Column(DateTime)
    
    # Overridden flag
    is_overridden = Column(Boolean, default=False)
    override_reason = Column(String)

    # Geofencing Tracking
    check_in_lat = Column(Float, nullable=True)
    check_in_lon = Column(Float, nullable=True)
    check_in_distance_m = Column(Float, nullable=True)
    check_in_in_range = Column(Boolean, nullable=True)

    check_out_lat = Column(Float, nullable=True)
    check_out_lon = Column(Float, nullable=True)
    check_out_distance_m = Column(Float, nullable=True)
    check_out_in_range = Column(Boolean, nullable=True)

    # Work Mode & WFH Linkage
    work_mode = Column(String(50), default="office")  # 'office', 'wfh', 'remote'
    wfh_request_id = Column(Integer, ForeignKey("wfh_requests.id"), nullable=True, index=True)

    employee = relationship("Employee", back_populates="attendances")
    wfh_request = relationship("WfhRequest", foreign_keys=[wfh_request_id])

    __table_args__ = (
        Index("idx_attendance_emp_date", "employee_id", "date"),
    )

