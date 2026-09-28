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
    DocumentType,
    EmployeeDocument,
)
from fastapi.middleware.cors import CORSMiddleware
from app.dependencies import get_password_hash, extract_token_from_request
from app.config import settings
from app.routers import auth, dashboard, company, employees, attendance, payroll, audit, departments, documents
from app.routers.api.v1 import api_v1_router


def ensure_schema_columns(db_engine):
    """Auto-migrate schema columns that were added after initial table creation across PostgreSQL & SQLite."""
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(db_engine)
        tables = inspector.get_table_names()

        # Table-to-Columns Explicit Schema Migration Map
        schema_definitions = {
            "attendance": {
                "is_overridden": "BOOLEAN DEFAULT FALSE",
                "override_reason": "VARCHAR(500)",
                "check_in_lat": "FLOAT",
                "check_in_lon": "FLOAT",
                "check_in_distance_m": "FLOAT",
                "check_in_in_range": "BOOLEAN DEFAULT FALSE",
                "check_out_lat": "FLOAT",
                "check_out_lon": "FLOAT",
                "check_out_distance_m": "FLOAT",
                "check_out_in_range": "BOOLEAN DEFAULT FALSE",
            },
            "company": {
                "tagline": "VARCHAR(255)",
                "currency_code": "VARCHAR(10) DEFAULT 'INR'",
                "support_email": "VARCHAR(255)",
                "website": "VARCHAR(255)",
                "standard_hours_per_day": "FLOAT DEFAULT 8.0",
                "half_day_threshold_hours": "FLOAT DEFAULT 4.5",
                "cin": "VARCHAR(100)",
                "gstin": "VARCHAR(100)",
                "pan": "VARCHAR(100)",
                "logo_url": "VARCHAR(500)",
                "logo_file_id": "VARCHAR(255)",
                "signature_url": "VARCHAR(500)",
                "signature_file_id": "VARCHAR(255)",
                "office_latitude": "FLOAT",
                "office_longitude": "FLOAT",
                "geofence_radius_meters": "INTEGER DEFAULT 200",
                "geofence_enabled": "BOOLEAN DEFAULT TRUE",
                "geofence_strict_mode": "BOOLEAN DEFAULT TRUE",
            },
            "employee_profiles": {
                "avatar_url": "VARCHAR(500)",
                "photo_file_id": "VARCHAR(255)",
                "uan_number": "VARCHAR(100)",
                "phone_number": "VARCHAR(50)",
                "home_address": "VARCHAR(500)",
                "city": "VARCHAR(100)",
                "state": "VARCHAR(100)",
                "country": "VARCHAR(100)",
                "gender": "VARCHAR(50)",
                "qualification": "VARCHAR(200)",
                "experience": "VARCHAR(200)",
                "aadhar_number": "VARCHAR(100)",
                "pan_number": "VARCHAR(100)",
                "is_geofence_exempt": "BOOLEAN DEFAULT FALSE",
            },
            "employees": {
                "department_id": "INTEGER",
                "designation_id": "INTEGER",
                "reset_token": "VARCHAR(255)",
                "reset_token_expiry": "TIMESTAMP",
                "is_active": "BOOLEAN DEFAULT TRUE",
                "role": "VARCHAR(50) DEFAULT 'employee'",
                "joining_date": "DATE",
            },
            "payslips": {
                "generated_on": "DATE",
                "payable_days": "INTEGER DEFAULT 22",
                "days_worked": "FLOAT DEFAULT 0.0",
                "basic": "FLOAT DEFAULT 0.0",
                "hra": "FLOAT DEFAULT 0.0",
                "allowances": "FLOAT DEFAULT 0.0",
                "bonus": "FLOAT DEFAULT 0.0",
                "pf": "FLOAT DEFAULT 0.0",
                "tax": "FLOAT DEFAULT 0.0",
                "other_deductions": "FLOAT DEFAULT 0.0",
                "net_salary": "FLOAT DEFAULT 0.0",
                "status": "VARCHAR(50) DEFAULT 'draft'",
            },
            "document_types": {
                "category": "VARCHAR(100) DEFAULT 'KYC'",
                "is_mandatory": "BOOLEAN DEFAULT FALSE",
                "who_uploads": "VARCHAR(50) DEFAULT 'employee'",
                "allowed_extensions": "VARCHAR(200) DEFAULT 'pdf,jpg,jpeg,png,webp,docx'",
                "max_file_size_mb": "INTEGER DEFAULT 10",
                "department_id": "INTEGER",
                "is_active": "BOOLEAN DEFAULT TRUE",
                "display_order": "INTEGER DEFAULT 0",
                "created_at": "TIMESTAMP",
            },
            "employee_documents": {
                "document_type_id": "INTEGER",
                "custom_title": "VARCHAR(200)",
                "file_name": "VARCHAR(500)",
                "file_url": "VARCHAR(1000)",
                "file_size": "INTEGER DEFAULT 0",
                "mime_type": "VARCHAR(100) DEFAULT 'application/pdf'",
                "status": "VARCHAR(50) DEFAULT 'pending'",
                "verified_by_id": "INTEGER",
                "verified_at": "TIMESTAMP",
                "rejection_reason": "TEXT",
                "uploaded_at": "TIMESTAMP",
            },
        }

        # 1. First run explicit mappings
        with db_engine.begin() as conn:
            for table_name, cols_dict in schema_definitions.items():
                if table_name in tables:
                    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
                    for col_name, col_type in cols_dict.items():
                        if col_name not in existing_cols:
                            try:
                                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                                print(f"[Schema Migration] Added column {col_name} to {table_name}")
                            except Exception as col_err:
                                print(f"[Schema Migration Col Warning] {table_name}.{col_name}: {col_err}")

        # 2. Automatically sync any model columns declared in Base.metadata
        from app.database import Base
        with db_engine.begin() as conn:
            for table_name, table in Base.metadata.tables.items():
                if table_name in tables:
                    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
                    for col in table.columns:
                        if col.name not in existing_cols:
                            try:
                                col_type_str = col.type.compile(db_engine.dialect)
                                default_str = ""
                                if str(col.type).upper().startswith("BOOL"):
                                    default_str = " DEFAULT FALSE"
                                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type_str}{default_str}"))
                                print(f"[Dynamic Schema Migration] Added {table_name}.{col.name} ({col_type_str})")
                            except Exception as col_err:
                                print(f"[Dynamic Schema Migration Warning] {table_name}.{col.name}: {col_err}")

    except Exception as e:
        print(f"[Schema Migration Warning] {e}")


# Run initial column checks on module load
ensure_schema_columns(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and seed default super admin."""
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns(engine)
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

        # Seed standard dynamic document types if empty
        if db.query(DocumentType).count() == 0:
            defaults = [
                DocumentType(
                    title="Aadhaar Card",
                    code="aadhaar_card",
                    description="Upload clear scan of Aadhaar Card front and back in a single PDF or image.",
                    category="KYC",
                    is_mandatory=True,
                    who_uploads="employee",
                    allowed_extensions="pdf,jpg,jpeg,png,webp",
                    display_order=1,
                ),
                DocumentType(
                    title="PAN Card",
                    code="pan_card",
                    description="Mandatory for TDS and payroll taxation processing.",
                    category="KYC",
                    is_mandatory=True,
                    who_uploads="employee",
                    allowed_extensions="pdf,jpg,jpeg,png,webp",
                    display_order=2,
                ),
                DocumentType(
                    title="Highest Degree Certificate",
                    code="highest_degree",
                    description="Graduation / Post-Graduation degree certificate or consolidated marksheets.",
                    category="Education",
                    is_mandatory=True,
                    who_uploads="employee",
                    allowed_extensions="pdf,jpg,jpeg,png,webp",
                    display_order=3,
                ),
                DocumentType(
                    title="Resume / Curriculum Vitae (CV)",
                    code="resume_cv",
                    description="Updated professional resume or CV.",
                    category="Experience",
                    is_mandatory=True,
                    who_uploads="employee",
                    allowed_extensions="pdf,docx,doc",
                    display_order=4,
                ),
                DocumentType(
                    title="Previous Relieving Letter",
                    code="previous_relieving_letter",
                    description="Relieving letter or service certificate from your previous employer (if applicable).",
                    category="Experience",
                    is_mandatory=False,
                    who_uploads="employee",
                    allowed_extensions="pdf,jpg,jpeg,png,webp",
                    display_order=5,
                ),
                DocumentType(
                    title="Signed Offer Letter & NDA",
                    code="signed_offer_letter",
                    description="Official company signed appointment letter and non-disclosure agreement.",
                    category="Company Letters",
                    is_mandatory=True,
                    who_uploads="admin_only",
                    allowed_extensions="pdf,docx,doc",
                    display_order=6,
                ),
            ]
            db.add_all(defaults)
            db.commit()
            print("Seeded 6 default dynamic Document Types.")
    finally:
        db.close()
    yield  # app runs


app = FastAPI(
    title="TURTU HRMS API & Portal",
    description="Full-featured enterprise HRMS backend with REST API v1 and interactive web portal.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for SPA (React / Next.js / Vue) and Mobile (Flutter / React Native)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.utils.timezone import get_ist_today, get_ist_now

@app.middleware("http")
async def add_attendance_state_middleware(request: Request, call_next):
    request.state.is_checked_in = False
    request.state.active_check_in = None
    request.state.active_check_in_iso = ""
    request.state.last_check_out = None
    request.state.accumulated_seconds = 0
    request.state.accumulated_time_str = "00:00:00"
    
    token = extract_token_from_request(request)
    if token:
        db = SessionLocal()
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email = payload.get("sub")
            if email:
                user = db.query(Employee).filter(Employee.email == email).first()
                if user and user.role != "admin":
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
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
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


import traceback
import logging

logger = logging.getLogger("uvicorn.error")

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"[500 Error on {request.method} {request.url.path}]:\n{tb}")
    print(f"[500 Error on {request.method} {request.url.path}]:\n{tb}", flush=True)

    accept = request.headers.get("accept", "")
    path = request.url.path
    is_api = (
        "application/json" in accept
        or path.startswith("/api")
        or "/api/" in path
    )

    if is_api:
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred. Please check server logs."},
        )

    safe_target = get_safe_redirect(request, default="/dashboard")
    redirect_url = append_query_param(safe_target, "error", f"Server error: {str(exc) or 'An unexpected error occurred.'}")
    return RedirectResponse(url=redirect_url, status_code=303)


# Include Web Routers (Jinja2 / SSR)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(payroll.router)
app.include_router(company.router)
app.include_router(audit.router)
app.include_router(departments.router)
app.include_router(documents.router)

# Include REST API v1 Routers (JSON / Mobile / SPA)
app.include_router(api_v1_router)

@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
