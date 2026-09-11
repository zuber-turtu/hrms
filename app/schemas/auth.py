from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    email: str
    password: str


class UserSummary(BaseModel):
    id: int
    name: str
    email: str
    role: str
    department_id: Optional[int] = None
    designation_id: Optional[int] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserSummary


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
