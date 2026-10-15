# 🗄️ HRMS Database Migrations System

This directory houses all versioned database schema migrations for the HRMS platform. It is engineered to support **MySQL 8.0+ in Production (AWS RDS / GCP Cloud SQL / DigitalOcean)**, **PostgreSQL**, and **SQLite (Local Development)** seamlessly and idempotently.

---

## 📁 Directory Structure

```
migrations/
├── README.md                          # Documentation & instructions
├── run_migrations.py                  # CLI migration runner (Python/SQLAlchemy)
├── versions/                          # Sequential Python migration scripts
│   ├── 001_initial_baseline.py        # Baseline schema verification
│   ├── 002_company_zones_and_settings.py # Zones, geofence, and settings
│   ├── 003_snapshot_payslip_bank_details.py # Point-in-time bank snapshot
│   └── 004_payslip_emailed_at.py      # Emailed_at dispatch timestamp
└── sql/                               # Standalone SQL scripts (for MySQL CLI / phpMyAdmin)
    ├── 002_company_zones_and_settings.sql
    ├── 003_snapshot_payslip_bank_details.sql
    └── 004_payslip_emailed_at.sql
```

---

## 🚀 How to Run Migrations

### 1. In Production (Live Deployment)

Whenever you deploy new code to production via `git pull`:

```bash
cd /var/www/hrms

# 1. Pull the latest code
sudo -u hrms git pull origin main

# 2. Check pending migrations (optional preview)
sudo -u hrms /var/www/hrms/venv/bin/python migrations/run_migrations.py --status

# 3. Apply all pending migrations safely
sudo -u hrms /var/www/hrms/venv/bin/python migrations/run_migrations.py

# 4. Gracefully reload the application
sudo systemctl reload hrms
```

The runner automatically connects to the database specified in `/var/www/hrms/.env` (`DATABASE_URL`), tracks execution in the `schema_migrations` table, and ensures migrations only execute **once**.

---

### 2. In Local Development

```bash
# Check status
python migrations/run_migrations.py --status

# Dry-run preview
python migrations/run_migrations.py --dry-run

# Run migrations
python migrations/run_migrations.py
```

---

## 🛡️ Migration Tracking Table (`schema_migrations`)

The migration runner creates and maintains an internal audit table:

| Column | Type | Description |
| :--- | :--- | :--- |
| `version` | `VARCHAR(100)` | Sequential number identifier (e.g. `001`, `002`) |
| `name` | `VARCHAR(255)` | Full migration name (e.g. `002_company_zones_and_settings`) |
| `applied_at` | `TIMESTAMP` | UTC timestamp when migration was applied |

---

## ✍️ How to Add a New Migration

When making schema changes (e.g., adding a table, adding a column, altering indexes):

1. **Create a new file in `migrations/versions/`** using sequential 3-digit numbering:
   `migrations/versions/003_add_new_feature_table.py`

2. **Implement the `upgrade(conn)` function**:
   ```python
   from sqlalchemy import inspect, text

   def upgrade(conn):
       inspector = inspect(conn)
       tables = inspector.get_table_names()

       # Add column safely if missing (works across MySQL, Postgres, SQLite)
       if "employees" in tables:
           existing_cols = {c["name"] for c in inspector.get_columns("employees")}
           if "new_field" not in existing_cols:
               conn.execute(text("ALTER TABLE employees ADD COLUMN new_field VARCHAR(100)"))
               print("    [+] Added employees.new_field")
   ```

3. **(Optional) Add direct MySQL script in `migrations/sql/`**:
   `migrations/sql/003_add_new_feature_table.sql` for DBAs or direct CLI execution.

4. **Test locally**:
   ```bash
   python migrations/run_migrations.py
   ```
