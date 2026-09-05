from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from jose import jwt
import datetime

from app.database import engine, Base, SessionLocal
from app.models import Company, Employee, Attendance, Payslip, AuditLog  # ensure all models imported so tables are created
from app.dependencies import get_password_hash
from app.config import settings
from app.routers import auth, dashboard, company, employees, attendance, payroll, audit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables and seed default super admin."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(Employee).filter(Employee.email == "admin@hrms.local").first()
        if not admin:
            admin = Employee(
                name="Admin",
                email="admin@hrms.local",
                hashed_password=get_password_hash("Admin@123"),
                role="admin",
                department="Management",
                designation="System Administrator",
            )
            db.add(admin)
            db.commit()
            print("Seeded default admin: admin@hrms.local / Admin@123")
        elif admin.role != "admin":
            admin.role = "admin"
            db.commit()
    finally:
        db.close()
    yield  # app runs


app = FastAPI(title="Dynamic HRMS", lifespan=lifespan)

@app.middleware("http")
async def add_attendance_state_middleware(request: Request, call_next):
    request.state.is_checked_in = False
    request.state.active_check_in = None
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
                    today = datetime.date.today()
                    attendance_today = db.query(Attendance).filter(
                        Attendance.employee_id == user.id,
                        Attendance.date == today
                    ).order_by(Attendance.check_in.asc()).all()
                    
                    accumulated_seconds = 0
                    active = None
                    for r in attendance_today:
                        if r.check_out:
                            diff = (r.check_out - r.check_in).total_seconds()
                            accumulated_seconds += max(0, diff)
                        else:
                            active = r
                            
                    request.state.accumulated_seconds = int(accumulated_seconds)
                    hrs = request.state.accumulated_seconds // 3600
                    mins = (request.state.accumulated_seconds % 3600) // 60
                    secs = request.state.accumulated_seconds % 60
                    request.state.accumulated_time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                    
                    if active:
                        request.state.is_checked_in = True
                        request.state.active_check_in = active.check_in
                    elif attendance_today:
                        request.state.last_check_out = attendance_today[-1].check_out
        except Exception:
            pass
        finally:
            db.close()
            
    response = await call_next(request)
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(company.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(payroll.router)
app.include_router(audit.router)


@app.get("/")
def read_root():
    return RedirectResponse(url="/login")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

