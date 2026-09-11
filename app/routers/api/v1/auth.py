from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from app.database import get_db
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.dependencies import (
    verify_password,
    get_password_hash,
    create_access_token,
    require_auth,
)
from app.config import settings
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserSummary,
    ChangePasswordRequest,
)
from app.schemas.employee import EmployeeOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def api_login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate employee via email and password, returning JWT access token.
    """
    clean_email = payload.email.strip().lower()
    user = db.query(Employee).filter(Employee.email == clean_email).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact HR.",
        )

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "user_id": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    user_summary = UserSummary(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        department_id=user.department_id,
        designation_id=user.designation_id,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=user_summary,
    )


@router.get("/me", response_model=EmployeeOut)
async def api_get_current_user_profile(
    current_user: Employee = Depends(require_auth),
):
    """
    Retrieve full profile and permissions of the currently authenticated user.
    """
    return current_user


@router.post("/change-password")
async def api_change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """
    Change password for the current authenticated user.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password does not match.",
        )

    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long.",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CHANGE_PASSWORD",
        entity="Employee",
        entity_id=current_user.id,
        old_value="[PROTECTED]",
        new_value="[PROTECTED]",
    )
    db.add(audit)
    db.commit()

    return {"message": "Password changed successfully."}
