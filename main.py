from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from jose import jwt
import datetime

from app.database import engine, Base, SessionLocal
from app.models import (
    Company,
    Employee,
    Department,
    Designation,
    EmployeeProfile,
    EmployeeBankAccount,
    EmployeeEmergencyContact,
    SalaryStructure,
    Attendance,
    Payslip,
    AuditLog,
)
from app.dependencies import get_password_hash
from app.config import settings
from app.routers import auth, dashboard, company, employees, attendance, payroll, audit, departments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and seed default super admin."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(Employee).filter(Employee.role == "admin").first()
        if not admin:
            dept = db.query(Department).filter(Department.name == "Management").first()
            if not dept:
                dept = Department(name="Management", code="MGMT")
                db.add(dept)
                db.flush()
            desig = db.query(Designation).filter(Designation.title == "System Administrator").first()
            if not desig:
                desig = Designation(title="System Administrator", department_id=dept.id)
                db.add(desig)
                db.flush()
            admin = Employee(
                name="Admin",
                email="admin@hrms.local",
                hashed_password=get_password_hash("Admin@123"),
                role="admin",
                department_id=dept.id,
                designation_id=desig.id,
            )
            db.add(admin)
            db.flush()
            admin_profile = EmployeeProfile(employee_id=admin.id)
            admin_salary = SalaryStructure(employee_id=admin.id, base_salary=100000.0)
            db.add(admin_profile)
            db.add(admin_salary)
            db.commit()
            print("Seeded default admin: admin@hrms.local / Admin@123")
        elif admin.role != "admin":
            admin.role = "admin"
            db.commit()
    finally:
        db.close()
    yield  # app runs


app = FastAPI(title="TURTU HRMS", lifespan=lifespan)

from app.utils.timezone import get_ist_today, get_ist_now

@app.middleware("http")
async def add_attendance_state_middleware(request: Request, call_next):
    request.state.is_checked_in = False
    request.state.active_check_in = None
    request.state.active_check_in_iso = ""
    request.state.last_check_out = None
    request.state.accumulated_seconds = 0
    request.state.accumulated_time_str = "00:00:00"
    
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        db = SessionLocal()
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email = payload.get("sub")
            if email:
                user = db.query(Employee).filter(Employee.email == email).first()
                if user:
                    today = get_ist_today()
                    # Query all logs today in Indian Standard Time
                    today_logs = db.query(Attendance).filter(
                        Attendance.employee_id == user.id,
                        Attendance.date == today
                    ).order_by(Attendance.check_in.asc()).all()
                    
                    accumulated = 0
                    active_checkin = None
                    last_out = None
                    
                    for log in today_logs:
                        if log.check_in and log.check_out:
                            diff = (log.check_out - log.check_in).total_seconds()
                            if diff > 0:
                                accumulated += diff
                            last_out = log.check_out
                        elif log.check_in and not log.check_out:
                            active_checkin = log.check_in
                    
                    if active_checkin:
                        request.state.is_checked_in = True
                        request.state.active_check_in = active_checkin
                        request.state.active_check_in_iso = f"{active_checkin.strftime('%Y-%m-%dT%H:%M:%S')}+05:30"
                        request.state.accumulated_seconds = int(accumulated)
                    else:
                        request.state.is_checked_in = False
                        request.state.last_check_out = last_out
                        request.state.accumulated_seconds = int(accumulated)
                        hrs = int(accumulated // 3600)
                        mins = int((accumulated % 3600) // 60)
                        secs = int(accumulated % 60)
                        request.state.accumulated_time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        except Exception:
            pass
        finally:
            db.close()

    response = await call_next(request)
    return response

@app.middleware("http")
async def add_security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from app.utils.security import get_safe_redirect, append_query_param

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Browser Probe Endpoints (Chrome DevTools, favicon)
@app.get("/favicon.ico", include_in_schema=False)
@app.get("/.well-known/{rest_of_path:path}", include_in_schema=False)
async def browser_probe_handler():
    return Response(status_code=204)

# Global Exception Handlers to Prevent Raw JSON Errors on Web Forms
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    accept = request.headers.get("accept", "")
    path = request.url.path
    is_api = (
        "application/json" in accept
        or path.startswith("/api")
        or "/api/" in path
        or path.startswith("/.well-known")
        or path.startswith("/static")
        or path == "/favicon.ico"
        or path.endswith((".json", ".ico", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".map", ".txt", ".xml"))
    )

    if is_api:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    # Extract friendly missing/invalid field names
    missing_fields = []
    other_errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = str(loc[-1]) if loc else "field"
        clean_field = field.replace("_", " ").title()
        err_type = err.get("type", "")
        if "missing" in err_type or "required" in err.get("msg", "").lower():
            missing_fields.append(clean_field)
        else:
            other_errors.append(f"{clean_field}: {err.get('msg', 'invalid value')}")

    parts = []
    if missing_fields:
        parts.append(f"Required fields missing: {', '.join(missing_fields)}")
    if other_errors:
        parts.append("; ".join(other_errors))

    error_message = ". ".join(parts) if parts else "Please provide all required form inputs."

    safe_target = get_safe_redirect(request, default="/dashboard")
    redirect_url = append_query_param(safe_target, "error", error_message)
    return RedirectResponse(url=redirect_url, status_code=303)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    accept = request.headers.get("accept", "")
    path = request.url.path
    is_api = (
        "application/json" in accept
        or path.startswith("/api")
        or "/api/" in path
        or path.startswith("/.well-known")
        or path.startswith("/static")
        or path == "/favicon.ico"
        or path.endswith((".json", ".ico", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".map", ".txt", ".xml"))
    )

    if is_api or exc.status_code == 404 and (path.startswith("/.well-known") or path == "/favicon.ico"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    if exc.status_code == 401:
        return RedirectResponse(url="/login?error=Please+log+in+to+continue", status_code=303)

    if exc.status_code == 403:
        safe_target = get_safe_redirect(request, default="/dashboard")
        redirect_url = append_query_param(safe_target, "error", "Access Denied: You do not have permission for this action.")
        return RedirectResponse(url=redirect_url, status_code=303)

    if exc.status_code == 404:
        safe_target = get_safe_redirect(request, default="/dashboard")
        redirect_url = append_query_param(safe_target, "error", "The requested resource or page was not found.")
        return RedirectResponse(url=redirect_url, status_code=303)

    safe_target = get_safe_redirect(request, default="/dashboard")
    redirect_url = append_query_param(safe_target, "error", str(exc.detail))
    return RedirectResponse(url=redirect_url, status_code=303)


# Include Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(payroll.router)
app.include_router(company.router)
app.include_router(audit.router)
app.include_router(departments.router)

@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
