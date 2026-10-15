"""
Migration 001: Initial HRMS Baseline Schema
Creates all core relational tables if they do not already exist:
users, employees, departments, designations, employee_profiles,
salary_structures, attendance, payslips, audit_logs, document_types,
employee_documents, leave_types, leave_balances, leave_applications,
wfh_requests, company, office_locations, company_zones.
"""

from sqlalchemy import inspect
from app.database import Base


def upgrade(conn):
    print("  -> Verifying and creating baseline tables across metadata...")
    Base.metadata.create_all(bind=conn)
    
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    print(f"  -> Total tables confirmed in schema: {len(tables)}")


def downgrade(conn):
    # Baseline cannot be safely rolled back in production
    pass
