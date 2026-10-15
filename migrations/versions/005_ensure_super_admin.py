"""
Migration 005: Ensure Super Admin Account Exists
Safely elevates the default administrator or root admin to 'super_admin'
if no super admin account currently exists in the employees table.
"""

from sqlalchemy import inspect, text


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "employees" not in tables:
        return

    # Check if a super_admin already exists
    super_check = conn.execute(
        text("SELECT COUNT(*) FROM employees WHERE role = 'super_admin'")
    ).scalar()

    if super_check and super_check > 0:
        print("    [*] Super admin account already present. No upgrade needed.")
        return

    # Look for admin@hrms.local first
    default_admin = conn.execute(
        text("SELECT id, email FROM employees WHERE LOWER(email) = 'admin@hrms.local' LIMIT 1")
    ).fetchone()

    if default_admin:
        admin_id = default_admin[0]
        admin_email = default_admin[1]
        conn.execute(
            text("UPDATE employees SET role = 'super_admin', name = 'Super Admin' WHERE id = :emp_id"),
            {"emp_id": admin_id},
        )
        print(f"    [+] Successfully elevated '{admin_email}' (ID {admin_id}) to 'super_admin'.")
        return

    # Fallback: Elevate the earliest registered admin account
    first_admin = conn.execute(
        text("SELECT id, email FROM employees WHERE role = 'admin' ORDER BY id ASC LIMIT 1")
    ).fetchone()

    if first_admin:
        admin_id = first_admin[0]
        admin_email = first_admin[1]
        conn.execute(
            text("UPDATE employees SET role = 'super_admin' WHERE id = :emp_id"),
            {"emp_id": admin_id},
        )
        print(f"    [+] Successfully elevated earliest admin '{admin_email}' (ID {admin_id}) to 'super_admin'.")
    else:
        print("    [*] No existing admin found to elevate; startup lifespan will seed 'super_admin' automatically.")
