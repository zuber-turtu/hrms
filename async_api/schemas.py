"""
Pydantic v2 High-Speed Validation Schemas
Optimized with Strict Typing and Zero-Overhead Serializers
"""

import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ================= Base Configuration =================
class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


# ================= Health & Observability =================
class HealthResponse(BaseSchema):
    status: str = "alive"
    timestamp_utc: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class ReadinessResponse(BaseSchema):
    status: str = "ready"
    timestamp_utc: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    database_latency_ms: float
    redis_latency_ms: Optional[float] = None
    components: Dict[str, str]


# ================= User Schemas =================
class UserCreate(BaseSchema):
    tenant_id: str = Field(default="default", max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=100)
    role: str = Field(default="employee", max_length=50)


class UserResponse(BaseSchema):
    id: int
    tenant_id: str
    email: EmailStr
    name: str
    role: str
    is_active: bool
    created_at: datetime.datetime


# ================= Attendance Punch Schemas =================
class AttendancePunchCreate(BaseSchema):
    tenant_id: str = Field(default="default", max_length=50)
    user_id: int
    punch_type: str = Field(pattern="^(CHECK_IN|CHECK_OUT)$")
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    location_name: Optional[str] = Field(default=None, max_length=100)
    metadata: Optional[Dict[str, Any]] = None


class AttendancePunchResponse(BaseSchema):
    id: int
    tenant_id: str
    user_id: int
    punch_date: datetime.date
    punch_type: str
    timestamp_utc: datetime.datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    is_verified: bool


class AttendanceSummaryResponse(BaseSchema):
    user_id: int
    total_records: int
    punches: List[AttendancePunchResponse]
    cached: bool = False
    cache_ttl_remaining: Optional[int] = None
