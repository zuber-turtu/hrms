"""
HRMS SQLite to Supabase (PostgreSQL) Data Migration Tool
"""

import sys
import os
import argparse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

from app.database import Base
from app.models.company import Company
from app.models.department import Department, Designation
from app.models.employee import (
    Employee,
    EmployeeProfile,
    EmployeeBankAccount,
    EmployeeEmergencyContact,
    SalaryStructure,
)
from app.models.attendance import Attendance
from app.models.payroll import Payslip
from app.models.audit import AuditLog

MODELS_TO_MIGRATE = [
    Company,
    Department,
    Designation,
    Employee,
    EmployeeProfile,
    EmployeeBankAccount,
    EmployeeEmergencyContact,
    SalaryStructure,
    Attendance,
    Payslip,
    AuditLog,
]


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def migrate(source_url: str, target_url: str):
    source_url = normalize_url(source_url)
    target_url = normalize_url(target_url)

    print("=" * 60, flush=True)
    print(" HRMS Database Migration: SQLite -> Supabase (PostgreSQL)", flush=True)
    print("=" * 60, flush=True)
    print(f"Source DB : {source_url}", flush=True)
    print(f"Target DB : {target_url.split('@')[-1] if '@' in target_url else target_url}", flush=True)
    print("-" * 60, flush=True)

    source_engine = create_engine(source_url, connect_args={"check_same_thread": False})
    SourceSession = sessionmaker(bind=source_engine)
    source_db = SourceSession()

    try:
        target_engine = create_engine(target_url, pool_pre_ping=True)
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[+] Successfully connected to Supabase PostgreSQL!", flush=True)
    except Exception as e:
        print(f"[-] Failed to connect to Supabase: {e}", flush=True)
        sys.exit(1)

    print("[*] Re-creating schema tables on Supabase...", flush=True)
    Base.metadata.create_all(bind=target_engine)
    print("[+] All tables verified / created.", flush=True)

    # Truncate all tables in one command
    print("[*] Clearing existing target tables...", flush=True)
    table_names = [m.__tablename__ for m in MODELS_TO_MIGRATE]
    with target_engine.connect() as conn:
        try:
            conn.execute(text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE;"))
            conn.commit()
            print("[+] Tables truncated.", flush=True)
        except Exception as e:
            print(f"[-] Truncate info: {e}", flush=True)

    TargetSession = sessionmaker(bind=target_engine)
    target_db = TargetSession()

    total_migrated = 0
    migration_summary = []

    try:
        for model in MODELS_TO_MIGRATE:
            table_name = model.__tablename__
            columns = [c.name for c in model.__table__.columns]
            
            records = source_db.query(model).all()
            count = len(records)
            
            if count > 0:
                for record in records:
                    row_data = {col: getattr(record, col) for col in columns}
                    new_obj = model(**row_data)
                    target_db.add(new_obj)
                
                target_db.commit()
                total_migrated += count

            migration_summary.append((table_name, count))
            print(f"  -> Migrated {count:>4} record(s) into [{table_name}]", flush=True)

        print("\n[*] Updating PostgreSQL sequence counters for primary keys...", flush=True)
        with target_engine.connect() as conn:
            for model in MODELS_TO_MIGRATE:
                tbl = model.__tablename__
                try:
                    conn.execute(text(f"""
                        DO $$
                        DECLARE
                            seq_name text;
                            max_val bigint;
                        BEGIN
                            SELECT pg_get_serial_sequence('{tbl}', 'id') INTO seq_name;
                            IF seq_name IS NOT NULL THEN
                                EXECUTE 'SELECT COALESCE(MAX(id), 0) FROM {tbl}' INTO max_val;
                                IF max_val > 0 THEN
                                    EXECUTE 'SELECT setval(' || quote_literal(seq_name) || ', ' || max_val || ', true)';
                                END IF;
                            END IF;
                        END $$;
                    """))
                    conn.commit()
                except Exception:
                    pass

        print("[+] PostgreSQL sequences updated.", flush=True)

        print("\n" + "=" * 60, flush=True)
        print(" MIGRATION COMPLETED SUCCESSFULLY", flush=True)
        print("=" * 60, flush=True)
        for tbl, cnt in migration_summary:
            print(f"  • {tbl:<28}: {cnt:>5} records", flush=True)
        print("-" * 60, flush=True)
        print(f"  Total records migrated: {total_migrated}", flush=True)
        print("=" * 60, flush=True)

    except Exception as err:
        target_db.rollback()
        print(f"\n[-] Error during data migration: {err}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        source_db.close()
        target_db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate HRMS data from SQLite to Supabase")
    parser.add_argument(
        "--source",
        default="sqlite:///./hrms.db",
        help="Source SQLite database URL",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("DATABASE_URL", ""),
        help="Target Supabase PostgreSQL database URL",
    )

    args = parser.parse_args()
    target_db_url = args.target.strip()
    if not target_db_url or target_db_url.startswith("sqlite"):
        print("[-] Target Supabase URL is required in .env or via --target.")
        sys.exit(1)

    migrate(args.source, target_db_url)
