from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta
import uuid

from app.database import get_db
from app.models.employee import Employee
from app.dependencies import verify_password, create_access_token, get_password_hash, require_auth
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
    user = db.query(Employee).filter(Employee.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request, "auth/login.html", {"error": "Invalid email or password"}
        )

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
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth)
):
    if len(new_password) < 6:
        return templates.TemplateResponse(
            request, 
            "auth/change_password.html", 
            {"user": current_user, "error": "New password must be at least 6 characters long."}
        )

    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return templates.TemplateResponse(
        request, 
        "auth/change_password.html", 
        {"user": current_user, "success": "Password changed successfully."}
    )


