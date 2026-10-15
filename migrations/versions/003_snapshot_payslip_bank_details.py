"""
Migration 003: Snapshot Bank Details on Payslips
Adds point-in-time bank account columns to the `payslips` table:
- bank_name (VARCHAR(255) NULL)
- account_number (VARCHAR(255) NULL)
- ifsc_code (VARCHAR(100) NULL)

Ensures that finalized and paid payslips permanently preserve the bank details
active when the salary was disbursed, while draft payslips remain dynamically synced.
Backfills any existing finalized/paid payslips from the employee's active bank account.
"""

from sqlalchemy import inspect, text


def add_column_if_missing(conn, inspector, table_name, col_name, col_type_sql):
    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
    if col_name not in existing_cols:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type_sql}"))
        print(f"    [+] Added {table_name}.{col_name} ({col_type_sql})")


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "payslips" in tables:
        add_column_if_missing(conn, inspector, "payslips", "bank_name", "VARCHAR(255) NULL")
        add_column_if_missing(conn, inspector, "payslips", "account_number", "VARCHAR(255) NULL")
        add_column_if_missing(conn, inspector, "payslips", "ifsc_code", "VARCHAR(100) NULL")

        # Backfill existing finalized and paid payslips from active employee_bank_accounts
        if "employee_bank_accounts" in tables:
            try:
                dialect = conn.dialect.name
                if dialect == "mysql":
                    conn.execute(text("""
                        UPDATE payslips p
                        JOIN employee_bank_accounts b ON p.employee_id = b.employee_id
                        SET p.bank_name = b.bank_name,
                            p.account_number = b.account_number,
                            p.ifsc_code = b.ifsc_code
                        WHERE p.status IN ('finalized', 'paid') 
                          AND (p.bank_name IS NULL OR p.account_number IS NULL);
                    """))
                else:
                    # Generic / SQLite compatible backfill
                    conn.execute(text("""
                        UPDATE payslips
                        SET bank_name = (SELECT bank_name FROM employee_bank_accounts WHERE employee_bank_accounts.employee_id = payslips.employee_id),
                            account_number = (SELECT account_number FROM employee_bank_accounts WHERE employee_bank_accounts.employee_id = payslips.employee_id),
                            ifsc_code = (SELECT ifsc_code FROM employee_bank_accounts WHERE employee_bank_accounts.employee_id = payslips.employee_id)
                        WHERE status IN ('finalized', 'paid')
                          AND (bank_name IS NULL OR account_number IS NULL);
                    """))
                print("    [+] Backfilled bank details for existing finalized/paid payslips.")
            except Exception as e:
                print(f"    [!] Note during backfill: {e}")


def downgrade(conn):
    pass
