from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from app.database import Base

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date, nullable=False)
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

    employee = relationship("Employee", back_populates="attendances")
