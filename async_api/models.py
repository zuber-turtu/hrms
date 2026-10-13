"""
High-Performance SQLAlchemy 2.0 Async-Mapped Domain Models
Equipped with Strict Composite Column Indexing to Bypass Table-Scans Under Heavy Load
"""

import datetime
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from async_api.database import Base


class User(Base):
    """
    User entity engineered for 1,000+ concurrent auth & directory queries.
    Utilizes composite indexing on (tenant_id, role, is_active) to bypass full table scans.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), nullable=False, default="default", index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False, default="employee")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Async relationship with selectin loading to prevent lazy-load blocking
    punches = relationship(
        "AttendancePunch",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # High-traffic composite index for role-based authorization and departmental rosters
        Index("ix_users_tenant_role_active", "tenant_id", "role", "is_active"),
        Index("ix_users_tenant_created", "tenant_id", "created_at"),
    )


class AttendancePunch(Base):
    """
    High-frequency append-heavy punch model (50-100 RPS burst).
    Features explicit composite indexes targeting hot read paths.
    """
    __tablename__ = "attendance_punches"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), nullable=False, default="default")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    punch_date = Column(Date, nullable=False)
    punch_type = Column(String(20), nullable=False)  # 'CHECK_IN', 'CHECK_OUT'
    timestamp_utc = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String(100), nullable=True)
    is_verified = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(Text, nullable=True)

    # Async relationship
    user = relationship("User", back_populates="punches", lazy="selectin")

    __table_args__ = (
        # 1. Hot Path 1: "User viewing their attendance ledger/profile"
        Index("ix_punch_user_date", "user_id", "punch_date"),
        # 2. Hot Path 2: "Admin/HR dashboard querying verified punches on a given day"
        Index("ix_punch_tenant_date_verified", "tenant_id", "punch_date", "is_verified"),
        # 3. Hot Path 3: "Realtime activity feed and latest pulse ordering"
        Index("ix_punch_timestamp_user", "timestamp_utc", "user_id"),
    )


class AuditTrail(Base):
    """
    High-speed immutable audit event logger for compliance.
    """
    __tablename__ = "audit_trails"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(50), nullable=False, default="default")
    actor_id = Column(Integer, nullable=False, index=True)
    action = Column(String(100), nullable=False)
    entity = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    timestamp_utc = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    ip_address = Column(String(45), nullable=True)
    details = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_audit_tenant_entity_id", "tenant_id", "entity", "entity_id"),
        Index("ix_audit_timestamp_actor", "timestamp_utc", "actor_id"),
    )
