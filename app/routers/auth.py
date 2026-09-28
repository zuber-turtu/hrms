from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import secrets

from app.database import get_db
from app.models.employee import Employee
from app.models.audit import AuditLog
from app.dependencies import verify_password, create_access_token, get_password_hash, require_auth
from app.config import settings
from app.utils.rate_limiter import login_rate_limiter
from app.templates_config import templates
from app.services.email_service import (
    send_password_reset_email,
    send_password_changed_notification_email,
)
from app.utils.timezone import get_ist_now

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "auth/login.html")


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    clean_email = email.strip().lower()
    try:
        login_rate_limiter.check(request, identifier=clean_email)
    except HTTPException as e:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": e.detail},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = db.query(Employee).filter(Employee.email == clean_email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Invalid email or password"},
        )

    login_rate_limiter.reset(request, identifier=clean_email)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=access_token,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.COOKIE_NAME)
    return response


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    current_user: Employee = Depends(require_auth)
):
    return templates.TemplateResponse(request, "auth/change_password.html", {"user": current_user})


@router.post("/change-password")
async def change_password(
    request: Request,
    background_tasks: BackgroundTasks,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth)
):
    if not verify_password(current_password, current_user.hashed_password):
        return templates.TemplateResponse(
            request, 
            "auth/change_password.html", 
            {"user": current_user, "error": "Your current password is incorrect. If you forgot your password, please use the Email Verification link below."}
        )

    if len(new_password) < 6:
        return templates.TemplateResponse(
            request, 
            "auth/change_password.html", 
            {"user": current_user, "error": "New password must be at least 6 characters long."}
        )

    if confirm_password is not None and new_password != confirm_password:
        return templates.TemplateResponse(
            request, 
            "auth/change_password.html", 
            {"user": current_user, "error": "New passwords do not match. Please verify and re-enter."}
        )

    current_user.hashed_password = get_password_hash(new_password)
    db.commit()

    # Dispatch security notification email
    timestamp_str = get_ist_now().strftime("%Y-%m-%d %I:%M %p IST")
    background_tasks.add_task(
        send_password_changed_notification_email,
        to_email=current_user.email,
        recipient_name=current_user.name,
        changed_at=timestamp_str,
    )
    
    return templates.TemplateResponse(
        request, 
        "auth/change_password.html", 
        {"user": current_user, "success": "Password changed successfully. A security confirmation email has been sent."}
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "auth/forgot_password.html")


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    clean_email = email.strip().lower()
    
    # Rate limit password reset requests
    try:
        login_rate_limiter.check(request, identifier=f"forgot_{clean_email}")
    except HTTPException as e:
        return templates.TemplateResponse(
            request=request,
            name="auth/forgot_password.html",
            context={"error": e.detail},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = db.query(Employee).filter(Employee.email == clean_email, Employee.is_active == True).first()
    
    if user:
        # Generate 32-byte cryptographically secure token (url-safe)
        token = secrets.token_urlsafe(32)
        expire_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        expiry = datetime.utcnow() + timedelta(minutes=expire_minutes)

        user.reset_token = token
        user.reset_token_expiry = expiry
        db.commit()

        # Build absolute reset URL
        base_url = settings.APP_BASE_URL.rstrip("/") if settings.APP_BASE_URL else str(request.base_url).rstrip("/")
        reset_url = f"{base_url}/reset-password?token={token}"

        # Trigger background email dispatch
        background_tasks.add_task(
            send_password_reset_email,
            to_email=user.email,
            recipient_name=user.name,
            reset_url=reset_url,
        )

        # Audit log entry
        audit = AuditLog(
            actor_id=user.id,
            actor_email=user.email,
            action="PASSWORD_RESET_REQUESTED",
            entity="Employee",
            old_value=None,
            new_value=f"Password reset requested for {user.email}. Valid for {expire_minutes}m."
        )
        db.add(audit)
        db.commit()

    # Always return success message to prevent user enumeration attacks
    success_msg = f"If an account is associated with {clean_email}, we have sent a secure password reset link. Please check your inbox and spam folder."
    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password.html",
        context={"success": success_msg},
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str = Query(""),
    db: Session = Depends(get_db),
):
    if not token or not token.strip():
        return RedirectResponse(url="/forgot-password?error=Invalid+or+missing+password+reset+token", status_code=303)

    user = db.query(Employee).filter(Employee.reset_token == token.strip(), Employee.is_active == True).first()
    if not user:
        return RedirectResponse(url="/forgot-password?error=Invalid+or+expired+password+reset+link.+Please+request+a+new+one.", status_code=303)

    if user.reset_token_expiry and datetime.utcnow() > user.reset_token_expiry:
        return RedirectResponse(url="/forgot-password?error=This+password+reset+link+has+expired.+Please+request+a+new+one.", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="auth/reset_password.html",
        context={
            "token": token.strip(),
            "employee_name": user.name,
            "employee_email": user.email,
        }
    )


@router.post("/reset-password")
async def reset_password(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    clean_token = token.strip() if token else ""
    if not clean_token:
        return RedirectResponse(url="/forgot-password?error=Invalid+or+missing+reset+token", status_code=303)

    user = db.query(Employee).filter(Employee.reset_token == clean_token, Employee.is_active == True).first()
    if not user:
        return RedirectResponse(url="/forgot-password?error=Invalid+or+expired+password+reset+link.+Please+request+a+new+one.", status_code=303)

    if user.reset_token_expiry and datetime.utcnow() > user.reset_token_expiry:
        return RedirectResponse(url="/forgot-password?error=This+password+reset+link+has+expired.+Please+request+a+new+one.", status_code=303)

    if len(new_password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="auth/reset_password.html",
            context={
                "token": clean_token,
                "employee_name": user.name,
                "employee_email": user.email,
                "error": "Password must be at least 6 characters long.",
            }
        )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="auth/reset_password.html",
            context={
                "token": clean_token,
                "employee_name": user.name,
                "employee_email": user.email,
                "error": "Passwords do not match. Please verify and re-enter.",
            }
        )

    # Set new password & invalidate token immediately
    user.hashed_password = get_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    
    # Audit log
    audit = AuditLog(
        actor_id=user.id,
        actor_email=user.email,
        action="PASSWORD_RESET_COMPLETED",
        entity="Employee",
        old_value=None,
        new_value=f"Password successfully reset for {user.email}"
    )
    db.add(audit)
    db.commit()

    # Dispatch security confirmation email
    timestamp_str = get_ist_now().strftime("%Y-%m-%d %I:%M %p IST")
    background_tasks.add_task(
        send_password_changed_notification_email,
        to_email=user.email,
        recipient_name=user.name,
        changed_at=timestamp_str,
    )

    return RedirectResponse(
        url="/login?success=Password+reset+successfully!+You+can+now+sign+in+with+your+new+password.",
        status_code=303,
    )



