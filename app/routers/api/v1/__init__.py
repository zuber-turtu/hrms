from fastapi import APIRouter

from .auth import router as auth_router
from .employees import router as employees_router
from .attendance import router as attendance_router
from .departments import router as departments_router
from .payroll import router as payroll_router
from .company import router as company_router
from .audit import router as audit_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(employees_router)
api_v1_router.include_router(attendance_router)
api_v1_router.include_router(departments_router)
api_v1_router.include_router(payroll_router)
api_v1_router.include_router(company_router)
api_v1_router.include_router(audit_router)
