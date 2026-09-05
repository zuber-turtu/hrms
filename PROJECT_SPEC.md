# Dynamic Enterprise HRMS (FastAPI + Jinja2 + Tailwind)

## 1. Tech Stack & Environment
- **Backend:** Python 3.10+ with FastAPI, Uvicorn, SQLAlchemy, Pydantic, Jinja2 Templates.
- **Database:** SQLite (default for development) / PostgreSQL ready.
- **Authentication:** Session/Cookie-based JWT Auth with granular Role-Based Access Control (RBAC).
- **Frontend:** Server-Rendered Jinja2 HTML templates styled with Tailwind CSS (CDN) and Alpine.js / Vanilla JS for dynamic DOM interactions.
- **Document Engine:** ReportLab / Weasyprint for dynamic PDF salary slip generation.

## 2. Core Modules & Endpoints
1. **Authentication & Roles:**
   - Roles: `admin`, `hr_admin`, `manager`, `employee`.
   - Admin can dynamically promote/demote employee roles.
2. **Company Profile:**
   - Name, logo, registration details, currency symbol, weekly working days configuration.
3. **Employee Directory:**
   - Admin onboarding: Personal info, department, designation, joining date, bank details.
   - Employee self-service view.
4. **Attendance System:**
   - Daily Check-in / Check-out interface.
   - Monthly calendar view per employee.
   - Admin override capability to retroactively edit past attendance status with reason logging.
5. **Dynamic & Editable Payroll Engine:**
   - Base salary setup: Basic, HRA, Custom Allowances, PF, Tax.
   - Pro-rata calculation based on monthly attendance days worked vs total payable working days.
   - **Editable Payslip UI:** Interactive page where HR can edit date ranges, override line amounts, add one-time bonuses/deductions.
   - PDF export endpoint generating a professional salary slip.
6. **Audit Trail:**
   - Logs every administrative change (role update, attendance override, payslip edit).

## 3. Directory Structure
hrms_project/
├── app/
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── models/
│   │   ├── company.py
│   │   ├── employee.py
│   │   ├── attendance.py
│   │   ├── payroll.py
│   │   └── audit.py
│   ├── schemas/
│   ├── routers/
│   │   ├── auth.py
│   │   ├── company.py
│   │   ├── employees.py
│   │   ├── attendance.py
│   │   ├── payroll.py
│   │   └── audit.py
│   ├── services/
│   │   ├── payroll_calculator.py
│   │   └── pdf_generator.py
│   └── templates/
│       ├── base.html
│       ├── auth/
│       │   └── login.html
│       ├── dashboard/
│       │   ├── admin.html
│       │   └── employee.html
│       ├── company/
│       │   └── profile.html
│       ├── employees/
│       │   ├── list.html
│       │   └── create_or_edit.html
│       ├── attendance/
│       │   └── log.html
│       └── payroll/
│           ├── list.html
│           ├── edit_payslip.html
│           └── payslip_pdf_template.html
├── static/
│   ├── css/
│   └── js/
├── .env.example
├── requirements.txt
└── main.py