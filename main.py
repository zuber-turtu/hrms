from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.database import engine, Base, SessionLocal
from app.models import Company, Employee, Attendance, Payslip, AuditLog  # ensure all models imported so tables are created
from app.dependencies import get_password_hash

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
                first_name="Super",
                last_name="Admin",
                email="admin@hrms.local",
                hashed_password=get_password_hash("Admin@123"),
                role="super_admin",
                department="Management",
                designation="System Administrator",
            )
            db.add(admin)
            db.commit()
            print("Seeded default super admin: admin@hrms.local / Admin@123")
    finally:
        db.close()
    yield  # app runs


app = FastAPI(title="Dynamic HRMS", lifespan=lifespan)

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

