from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from app.utils.timezone import get_ist_now

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer)  # ID of the user performing the action
    actor_email = Column(String)
    action = Column(String)  # e.g., "ATTENDANCE_OVERRIDE", "ROLE_CHANGE"
    entity = Column(String)  # e.g., "Attendance", "Employee"
    entity_id = Column(Integer)
    old_value = Column(String) # Stored as JSON string or text
    new_value = Column(String) # Stored as JSON string or text
    timestamp = Column(DateTime, default=get_ist_now)
