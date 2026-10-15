"""
Migration 002: Company Zones, Multi-Site Geofencing & Dynamic Settings
Adds:
- company_zones table
- office_locations table
- Dynamic role_permissions, employee ID formatting, and lunch timings to company
- zone_id, hr_zone_scope, personal_email, company_email to employees
- Geofence exemption and lunch schedules to employee_profiles
- Location name tracking and GPS coordinates to attendance
"""

from sqlalchemy import inspect, text


def add_column_if_missing(conn, inspector, table_name, col_name, col_type_sql):
    """Safely adds a column to a table if it does not already exist."""
    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
    if col_name not in existing_cols:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type_sql}"))
        print(f"    [+] Added {table_name}.{col_name} ({col_type_sql})")


def upgrade(conn):
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    # 1. Ensure new tables exist
    from app.models.company import CompanyZone, OfficeLocation
    CompanyZone.__table__.create(bind=conn, checkfirst=True)
    OfficeLocation.__table__.create(bind=conn, checkfirst=True)
    print("    [+] Verified company_zones & office_locations tables.")

    # 2. Company table columns
    if "company" in tables:
        inspector = inspect(conn)
        company_cols = {
            "tagline": "VARCHAR(255)",
            "currency_code": "VARCHAR(10) DEFAULT 'INR'",
            "support_email": "VARCHAR(255)",
            "website": "VARCHAR(255)",
            "standard_hours_per_day": "FLOAT DEFAULT 8.0",
            "half_day_threshold_hours": "FLOAT DEFAULT 4.5",
            "lunch_break_hours": "FLOAT DEFAULT 1.0",
            "lunch_start_time": "VARCHAR(20) DEFAULT '13:00'",
            "lunch_end_time": "VARCHAR(20) DEFAULT '14:00'",
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
            "role_permissions": "TEXT",
            "employee_id_prefix": "VARCHAR(50) DEFAULT 'TU'",
            "employee_id_separator": "VARCHAR(10) DEFAULT '-'",
            "employee_id_include_year": "BOOLEAN DEFAULT TRUE",
            "employee_id_include_dept": "BOOLEAN DEFAULT TRUE",
            "employee_id_padding": "INTEGER DEFAULT 3",
        }
        for col, col_type in company_cols.items():
            add_column_if_missing(conn, inspector, "company", col, col_type)

    # 3. Employees table columns
    if "employees" in tables:
        inspector = inspect(conn)
        emp_cols = {
            "zone_id": "INTEGER",
            "hr_zone_scope": "VARCHAR(50) DEFAULT 'all'",
            "personal_email": "VARCHAR(255)",
            "company_email": "VARCHAR(255)",
            "token_version": "INTEGER DEFAULT 1",
        }
        for col, col_type in emp_cols.items():
            add_column_if_missing(conn, inspector, "employees", col, col_type)

    # 4. Employee Profiles table columns
    if "employee_profiles" in tables:
        inspector = inspect(conn)
        profile_cols = {
            "lunch_break_hours": "FLOAT DEFAULT 1.0",
            "lunch_start_time": "VARCHAR(20) DEFAULT '13:00'",
            "lunch_end_time": "VARCHAR(20) DEFAULT '14:00'",
            "is_geofence_exempt": "BOOLEAN DEFAULT FALSE",
        }
        for col, col_type in profile_cols.items():
            add_column_if_missing(conn, inspector, "employee_profiles", col, col_type)

    # 5. Attendance table columns
    if "attendance" in tables:
        inspector = inspect(conn)
        att_cols = {
            "check_in_lat": "FLOAT",
            "check_in_lon": "FLOAT",
            "check_in_distance_m": "FLOAT",
            "check_in_in_range": "BOOLEAN DEFAULT FALSE",
            "check_in_location_name": "VARCHAR(255)",
            "check_out_lat": "FLOAT",
            "check_out_lon": "FLOAT",
            "check_out_distance_m": "FLOAT",
            "check_out_in_range": "BOOLEAN DEFAULT FALSE",
            "check_out_location_name": "VARCHAR(255)",
            "work_mode": "VARCHAR(50) DEFAULT 'office'",
            "wfh_request_id": "INTEGER",
            "is_overridden": "BOOLEAN DEFAULT FALSE",
            "override_reason": "VARCHAR(500)",
        }
        for col, col_type in att_cols.items():
            add_column_if_missing(conn, inspector, "attendance", col, col_type)


def downgrade(conn):
    pass
