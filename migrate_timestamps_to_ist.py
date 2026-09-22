import sys
import datetime
from app.database import SessionLocal
from app.models import Attendance, AuditLog, Employee

# Cutoff ID for records created before the IST fix was deployed
MAX_ATTENDANCE_ID_TO_MIGRATE = 19
MAX_AUDIT_LOG_ID_TO_MIGRATE = 21

SHIFT_DELTA = datetime.timedelta(hours=5, minutes=30)


def run_migration(apply_changes: bool = False):
    db = SessionLocal()
    try:
        print("=" * 80)
        print(f"DATABASE TIMESTAMP MIGRATION TO IST (Apply = {apply_changes})")
        print("=" * 80)

        # 1. Attendance Records Migration
        attendances = (
            db.query(Attendance)
            .filter(Attendance.id <= MAX_ATTENDANCE_ID_TO_MIGRATE)
            .order_by(Attendance.id.asc())
            .all()
        )

        print(f"\n[ATTENDANCE] Found {len(attendances)} records to shift by +5h 30m:")
        for a in attendances:
            emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
            emp_name = emp.name if emp else f"Emp #{a.employee_id}"

            old_in = a.check_in
            old_out = a.check_out
            old_date = a.date

            new_in = old_in + SHIFT_DELTA if old_in else None
            new_out = old_out + SHIFT_DELTA if old_out else None
            new_date = new_in.date() if new_in else old_date

            print(f"  ID {a.id:2d} ({emp_name}):")
            print(f"    Check-In:  {old_in} -> {new_in}")
            print(f"    Check-Out: {old_out} -> {new_out}")
            if old_date != new_date:
                print(f"    Date:      {old_date} -> {new_date}")

            if apply_changes:
                a.check_in = new_in
                a.check_out = new_out
                a.date = new_date

        # 2. Audit Logs Migration
        audit_logs = (
            db.query(AuditLog)
            .filter(AuditLog.id <= MAX_AUDIT_LOG_ID_TO_MIGRATE)
            .order_by(AuditLog.id.asc())
            .all()
        )

        print(f"\n[AUDIT LOGS] Found {len(audit_logs)} records to shift by +5h 30m:")
        for log in audit_logs:
            old_ts = log.timestamp
            new_ts = old_ts + SHIFT_DELTA if old_ts else None

            print(f"  ID {log.id:2d} ({log.action}):")
            print(f"    Timestamp: {old_ts} -> {new_ts}")

            if apply_changes:
                log.timestamp = new_ts

        if apply_changes:
            db.commit()
            print("\n" + "=" * 80)
            print(">>> SUCCESS: All changes successfully committed to the database! <<<")
            print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print(">>> DRY-RUN COMPLETE: No changes were written. Use --apply to execute. <<<")
            print("=" * 80)

    except Exception as e:
        db.rollback()
        print(f"\nERROR during migration: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    apply_mode = "--apply" in sys.argv
    run_migration(apply_changes=apply_mode)
