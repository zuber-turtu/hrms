#!/usr/bin/env python3
"""
HRMS Super Admin CLI Management Utility
Use this script on your production or local server to grant 'super_admin' privileges
to any existing user, or create a brand new Super Admin account.

Usage:
    python promote_super_admin.py
    python promote_super_admin.py admin@hrms.local
    python promote_super_admin.py user@yourcompany.com
    python promote_super_admin.py --email admin@hrms.local --create --password Admin@123
"""

import sys
import os
import argparse

# Add application directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import func
from app.database import SessionLocal
from app.models import (
    Employee,
    Department,
    Designation,
    EmployeeProfile,
    SalaryStructure,
)
from app.dependencies import get_password_hash


def parse_args():
    parser = argparse.ArgumentParser(description="HRMS Super Admin Management Utility")
    parser.add_argument("email", nargs="?", help="Email of employee to promote or create as super_admin")
    parser.add_argument("--email", dest="flag_email", help="Alternative email argument")
    parser.add_argument("--password", dest="password", default=None, help="Password if creating a new user")
    parser.add_argument("--name", dest="name", default=None, help="Full name if creating a new user")
    parser.add_argument("--create", dest="create", action="store_true", help="Automatically create account if it does not exist")
    return parser.parse_args()


def main():
    args = parse_args()
    target_email = (args.flag_email or args.email or "").strip().lower()

    db = SessionLocal()
    try:
        if target_email:
            promote_or_create_user(db, target_email, args.name, args.password, auto_create=args.create)
            return

        # Interactive / Inspection Mode
        print("=" * 65)
        print("        HRMS SUPER ADMIN MANAGEMENT UTILITY")
        print("=" * 65)

        super_admins = db.query(Employee).filter(Employee.role == "super_admin").all()
        admins = db.query(Employee).filter(Employee.role == "admin").all()

        print("\n[*] Current Super Administrators:")
        if super_admins:
            for sa in super_admins:
                print(f"    - ID: {sa.id:<3} | Name: {sa.name:<20} | Email: {sa.email}")
        else:
            print("    (None found! Your system currently has NO super admin.)")

        print("\n[*] Current Administrators (Role: admin):")
        if admins:
            for a in admins:
                print(f"    - ID: {a.id:<3} | Name: {a.name:<20} | Email: {a.email}")
        else:
            print("    (None found.)")

        print("\n" + "-" * 65)
        try:
            email_input = input("Enter email address to promote to 'super_admin' [admin@hrms.local]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return

        if not email_input:
            email_input = "admin@hrms.local"

        promote_or_create_user(db, email_input, args.name, args.password, auto_create=args.create)

    finally:
        db.close()


def promote_or_create_user(db, email: str, name: str = None, password: str = None, auto_create: bool = False):
    emp = db.query(Employee).filter(func.lower(Employee.email) == email.lower()).first()

    if emp:
        old_role = emp.role
        emp.role = "super_admin"
        if emp.name in ("Admin", "admin"):
            emp.name = "Super Admin"
        db.commit()
        print(f"\n[SUCCESS] Successfully promoted '{emp.email}' from '{old_role}' to 'super_admin'!")
        print(f"User ID   : {emp.id}")
        print(f"Name      : {emp.name}")
        print(f"New Role  : {emp.role}")
        print("\nYou can now log in with full Super Administrator permissions.")
        return

    # User does not exist, offer to create
    print(f"\n[!] No user with email '{email}' exists in the database.")
    
    should_create = auto_create
    if not should_create:
        try:
            choice = input(f"Would you like to create a new Super Admin account for '{email}'? [Y/n]: ").strip().lower()
            should_create = choice in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            should_create = False

    if should_create:
        full_name = name or "Super Admin"
        if not name and not auto_create and sys.stdin.isatty():
            try:
                full_name = input("Enter full name [Super Admin]: ").strip() or "Super Admin"
            except (EOFError, KeyboardInterrupt):
                full_name = "Super Admin"

        raw_password = password or "Admin@123"
        if not password and not auto_create and sys.stdin.isatty():
            try:
                raw_password = input("Enter password [Admin@123]: ").strip() or "Admin@123"
            except (EOFError, KeyboardInterrupt):
                raw_password = "Admin@123"

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

        new_super = Employee(
            name=full_name,
            email=email,
            hashed_password=get_password_hash(raw_password),
            role="super_admin",
            department_id=dept.id,
            designation_id=desig.id,
            is_active=True,
        )
        db.add(new_super)
        db.flush()

        db.add(EmployeeProfile(employee_id=new_super.id))
        db.add(SalaryStructure(employee_id=new_super.id, base_salary=100000.0))
        db.commit()

        print(f"\n[SUCCESS] Created new Super Admin account '{email}'!")
        print(f"Email    : {email}")
        print(f"Password : {raw_password}")
        print(f"Role     : super_admin")
    else:
        print("[*] Aborted. No changes made.")


if __name__ == "__main__":
    main()
