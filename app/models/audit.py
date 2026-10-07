from sqlalchemy import Column, Integer, String, DateTime, Index
from app.database import Base
from app.utils.timezone import get_ist_now

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, index=True)  # ID of the user performing the action
    actor_email = Column(String, index=True)
    action = Column(String, index=True)  # e.g., "ATTENDANCE_OVERRIDE", "ROLE_CHANGE"
    entity = Column(String, index=True)  # e.g., "Attendance", "Employee"
    entity_id = Column(Integer, index=True)
    old_value = Column(String) # Stored as JSON string or text
    new_value = Column(String) # Stored as JSON string or text
    timestamp = Column(DateTime, default=get_ist_now, index=True)

    __table_args__ = (
        Index("idx_audit_timestamp_action", "timestamp", "action"),
    )

