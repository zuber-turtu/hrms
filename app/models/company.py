from sqlalchemy import Column, Integer, String, Float, Boolean
from app.database import Base

class Company(Base):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Acme Corp")
    address = Column(String, default="123 Enterprise Way")
    currency_symbol = Column(String, default="$")
    working_days_per_month = Column(Integer, default=22)
    cin = Column(String, nullable=True, default=None)
    gstin = Column(String, nullable=True, default=None)
    pan = Column(String, nullable=True, default=None)

    # Geofencing & Office Location
    office_latitude = Column(Float, nullable=True, default=None)
    office_longitude = Column(Float, nullable=True, default=None)
    geofence_radius_meters = Column(Integer, default=200)
    geofence_enabled = Column(Boolean, default=True)
    geofence_strict_mode = Column(Boolean, default=True)
