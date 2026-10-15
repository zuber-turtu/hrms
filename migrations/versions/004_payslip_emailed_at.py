"""
Migration 004: Add emailed_at column to payslips
Adds `emailed_at` (DATETIME NULL) to the `payslips` table to track when a payslip
notification and PDF statement was emailed to the employee.
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
        add_column_if_missing(conn, inspector, "payslips", "emailed_at", "DATETIME NULL")
