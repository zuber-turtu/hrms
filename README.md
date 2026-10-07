# Company HRMS — Modern Enterprise Human Resource Management System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg?style=flat&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.0+-38B2AC.svg?style=flat&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A dynamic, full-featured, enterprise-grade **Human Resource Management System (HRMS)** built with **FastAPI**, **SQLAlchemy 2.0**, **Jinja2**, and **Tailwind CSS**. Designed for modern organizations, featuring multi-database support (SQLite, MySQL, PostgreSQL), pluggable multi-cloud storage, GPS geofencing attendance, dynamic payroll calculation, PDF payslip generation, multi-tier leave workflows, and granular role-based access control.

> 📖 **Looking for deployment instructions?** See the full **[Complete Setup & Deployment Guide (SETUP.md)](SETUP.md)** for production Linux/Gunicorn/Nginx, Docker, and local development walkthroughs.

---

## 📑 Table of Contents
- [Setup & Deployment Guide (SETUP.md)](SETUP.md)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Directory Structure](#-directory-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start & Installation](#-quick-start--installation)
- [Database Setup & Configuration](#-database-setup--configuration)
  - [1. SQLite (Default)](#1-sqlite-default-zero-configuration)
  - [2. MySQL / MariaDB](#2-mysql--mariadb)
  - [3. PostgreSQL / Supabase](#3-postgresql--supabase)
- [Multi-Cloud Storage Setup](#-multi-cloud-storage-setup)
- [Email & SMTP Configuration](#-email--smtp-configuration)
- [Default Admin Credentials](#-default-admin-credentials)
- [API Documentation](#-api-documentation)
- [Keyboard Shortcuts & UI Features](#-keyboard-shortcuts--ui-features)
- [License](#-license)

---

## 🚀 Key Features

### 🏢 1. Company & Corporate Branding
- **Dynamic Identity**: Configurable company logo, stamp/signature, brand colors, slogan, website, and support email.
- **Statutory Details**: Enterprise registration fields including **CIN**, **GSTIN**, and **PAN**.
- **Customizable Employee ID Prefix**: Configure customized code prefixes (e.g. `Company-0001`, `ACME-0042`) with graceful fallback to standard sequential formatting (`#0001`).
- **Work Hours & Break Policies**: Flexible standard hours/day, half-day thresholds, and automated lunch break tracking.

### 📍 2. GPS Geofenced Attendance System
- **Geofencing Engine**: Validate check-in and check-out against company GPS coordinates (latitude, longitude) with configurable radius (in meters).
- **Enforcement Modes**: Strict mode (blocks out-of-range check-ins) and Lenient mode (flags records for review).
- **Exemptions & WFH**: Individual employee geofence exemption toggle and dedicated Work-From-Home (WFH) approval flow.
- **Attendance Logging**: Real-time topbar clock-in/out widget, daily logs, monthly calendar view, overtime tracking, and administrative overrides with audit logs.

### 👥 3. Comprehensive Employee Management
- **Full Employee Dossier**: Personal details, department, designation, joining date, qualifications, experience, and contact details.
- **Financial & Statutory Data**: Bank account details (Account number, IFSC, Bank name) and national IDs (Aadhaar, PAN, UAN).
- **Role-Based Access Control (RBAC)**: 4 pre-configured authorization tiers:
  - `admin` — Full platform control, company profile, audit logs, and employee role promotion.
  - `hr_admin` — Employee onboarding, department configuration, payroll editing, and leave approvals.
  - `manager` — Team attendance monitoring, leave approvals, and WFH management.
  - `employee` — Self-service dashboard, attendance clocking, leave requests, and payslip viewing.

### 🗂️ 4. Departments & Job Designations
- **Department Hierarchy**: Color-coded department cards with unique short codes.
- **Interactive Staff Roster**: Click any department or designation to open a live-search modal displaying all assigned team members, contact badges, and direct links to dossiers.

### 🏖️ 5. Leave & Absence Management
- **Dynamic Leave Types & Statutory Policies**: Full admin CRUD to create custom leave categories (e.g. *Casual Leave*, *Medical Leave*, *Earned Leave*, *Comp Off*, *Maternity*, *Paternity*, *Bereavement*, *Study Leave*, *LWP*) with custom quota days, color badges, paid/unpaid classification, and gender applicability rules.
- **Bulk Allocation Center**: One-click company/department-wide WFH scheduling, direct bulk leave grants (e.g., festival holidays), and annual quota allocation adjustments.
- **Approval Workflows**: Multi-tier review by HR and Managers with reason logging, rejection remarks, and live balance deductions.
- **WFH Requests**: Integrated Work-From-Home request lifecycle with geofence bypass upon approval.

### 💰 6. Dynamic Payroll & PDF Payslips
- **Salary Structures**: Configurable basic pay, HRA, special allowances, PF, income tax, and custom line deductions.
- **Pro-Rata Attendance Engine**: Automatically calculates net salary based on days worked vs. standard payable days in the month.
- **Interactive Payslip Editor**: Allows HR admins to edit earnings, apply one-time bonuses or deductions, and customize date ranges prior to locking.
- **PDF Generation**: High-fidelity, print-ready PDF salary slips with corporate logo, signature stamp, and breakdown tables powered by **ReportLab**.

### 📁 7. Multi-Cloud Document Vault
- **Document Categories**: KYC, academic certificates, experience letters, and company contracts with max size & extension restrictions.
- **Verification Pipeline**: Admin document verification, approval, rejection with feedback, and download audit.
- **5 Pluggable Storage Backends**:
  1. `local` — Local disk storage (`static/uploads/`).
  2. `supabase` — Supabase Cloud Storage.
  3. `gdrive` — Google Drive via Service Account.
  4. `cloudflare` — Cloudflare R2 (S3-compatible, zero egress fees).
  5. `s3` — AWS S3 or MinIO.

### 🎨 8. Modern UI/UX Experience
- Glassmorphism & sleek dark/light accent design system.
- **Collapsible Sidebar Rail**: Expandable/collapsible desktop navigation rail with smooth CSS transitions, tooltip hover popovers, and persistent state (`localStorage`).
- **Keyboard Shortcut**: `Ctrl + B` (or `Cmd + B` on macOS) to instantly toggle the sidebar navigation.

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) |
| **ASGI Server** | [Uvicorn](https://www.uvicorn.org/) with Hot Reload |
| **ORM & Database Layer** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) with Connection Pooling |
| **Database Engines** | SQLite, MySQL / MariaDB (`pymysql`), PostgreSQL / Supabase (`psycopg2`) |
| **Template Engine** | [Jinja2](https://jinja.palletsprojects.com/) |
| **Styling & Icons** | [Tailwind CSS](https://tailwindcss.com/), [FontAwesome](https://fontawesome.com/), Custom Vanilla CSS |
| **Authentication** | JWT (JSON Web Tokens) via `python-jose` stored in secure HTTP-only cookies |
| **Password Hashing** | `passlib` with `bcrypt` |
| **PDF Generation** | [ReportLab](https://www.reportlab.com/) |
| **Cloud Storage** | Supabase Storage, Google Drive API, Boto3 (S3 / R2) |

---

## 📂 Directory Structure

```text
hrms/
├── app/
│   ├── config.py                 # Pydantic / dotenv global settings
│   ├── database.py               # Multi-engine SQLAlchemy session manager
│   ├── dependencies.py           # Auth guards, token extractors & RBAC
│   ├── templates_config.py       # Custom Jinja filters & global helpers
│   ├── models/                   # SQLAlchemy declarative models
│   │   ├── company.py            # Company settings & branding
│   │   ├── employee.py           # Employee profile, bank, emergency contacts
│   │   ├── department.py         # Departments & designations
│   │   ├── attendance.py         # Daily logs, GPS checks & WFH requests
│   │   ├── leave.py              # Leave types, balances & applications
│   │   ├── payroll.py            # Salary structures & monthly payslips
│   │   ├── document.py           # Document types & uploaded files
│   │   └── audit.py              # Administrative action audit trail
│   ├── schemas/                  # Pydantic request & response schemas
│   ├── routers/                  # Server-rendered HTML routers
│   │   ├── auth.py               # Login, logout, password resets
│   │   ├── dashboard.py          # Role-based dashboard views
│   │   ├── company.py            # Company settings & profile
│   │   ├── employees.py          # Employee directory & profile management
│   │   ├── departments.py        # Departments, roles & staff rosters
│   │   ├── attendance.py         # Clock-in/out, logs & overrides
│   │   ├── leaves.py             # Leave applications & approvals
│   │   ├── payroll.py            # Salary calculation & payslip editor
│   │   ├── documents.py          # Document verification & downloads
│   │   ├── audit.py              # Audit log viewer
│   │   └── api/v1/               # Headless REST API endpoints
│   ├── services/                 # Business logic services
│   │   ├── payroll_calculator.py # Pro-rata salary computations
│   │   ├── pdf_generator.py      # ReportLab PDF payslip engine
│   │   └── storage/              # Storage backends (Local, Supabase, GDrive, S3)
│   └── templates/                # Jinja2 HTML templates
│       ├── base.html             # Master layout with collapsible sidebar
│       ├── auth/                 # Login & password recovery pages
│       ├── dashboard/            # Admin & employee dashboards
│       ├── company/              # Company profile & settings
│       ├── employees/            # Employee list, dossiers & edit forms
│       ├── departments/          # Department cards & staff modals
│       ├── attendance/           # Clock widget & calendar logs
│       ├── leaves/               # Leave portal & management
│       ├── payroll/              # Payroll list, editor & payslip views
│       └── documents/            # Document vault & upload forms
├── static/
│   ├── css/styles.css            # Custom CSS & animation rules
│   ├── js/                       # Client-side scripts
│   └── uploads/                  # Local storage directory
├── .env.example                  # Environment configuration template
├── requirements.txt              # Project dependencies
├── main.py                       # FastAPI application entrypoint & lifespan
└── README.md                     # Project documentation
```

---

## 📋 Prerequisites

Ensure you have the following installed on your system:
- **Python 3.10+** (Python 3.11 or 3.12 recommended)
- **Git**
- *(Optional)* **MySQL** (5.7+ / 8.0+) or **PostgreSQL** if not using SQLite.

---

## ⚡ Quick Start & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-organization/hrms.git
cd hrms
```

### 2. Create and Activate a Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

### 5. Launch the Development Server
```bash
uvicorn main:app --reload --port 8000
```

Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🗄 Database Setup & Configuration

The application supports **SQLite**, **MySQL / MariaDB**, and **PostgreSQL / Supabase** out of the box. Database tables and schema columns are automatically synchronized when the application starts.

### 1. SQLite (Default, Zero-Configuration)
Best for local development and testing. No database server required.
```env
DATABASE_URL=sqlite:///./hrms.db
```

---

### 2. MySQL / MariaDB
1. Create a database in MySQL:
   ```sql
   CREATE DATABASE hrms_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. Set the `DATABASE_URL` in your `.env`:
   ```env
   DATABASE_URL=mysql+pymysql://YOUR_USER:YOUR_PASSWORD@localhost:3306/hrms_db
   ```
   *(e.g., `DATABASE_URL=mysql+pymysql://root:root123@localhost:3306/hrms_db`)*

---

### 3. PostgreSQL / Supabase
1. Create a PostgreSQL database or obtain your Supabase connection string.
2. Set the `DATABASE_URL` in your `.env`:
   ```env
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/hrms_db
   ```
   *For Supabase Transaction Pooler:*
   ```env
   DATABASE_URL=postgresql://postgres.[REF]:[PASS]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
   ```

---

## ☁️ Multi-Cloud Storage Setup

Configure the `STORAGE_PROVIDER` setting in `.env` to select your document vault storage engine:

| Provider | Setting | Required Credentials |
|---|---|---|
| **Local Disk** | `STORAGE_PROVIDER=local` | None (saved to `static/uploads/`) |
| **Supabase Storage** | `STORAGE_PROVIDER=supabase` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET_NAME` |
| **Google Drive** | `STORAGE_PROVIDER=gdrive` | `GDRIVE_SERVICE_ACCOUNT_FILE`, `GDRIVE_FOLDER_ID` |
| **Cloudflare R2** | `STORAGE_PROVIDER=cloudflare` | `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` |
| **AWS S3 / MinIO** | `STORAGE_PROVIDER=s3` | `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION_NAME` |

---

## 📧 Email & SMTP Configuration

To enable password reset emails and system notifications via Gmail or custom SMTP:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME="HRMS Notifications"
SMTP_USE_TLS=True

APP_BASE_URL=http://localhost:8000
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30
```

> [!TIP]
> If using Gmail, generate an **App Password** from your Google Account settings (Security → 2-Step Verification → App Passwords).

---

## 🔑 Default Admin Credentials

Upon initial launch, the system automatically initializes a default super-administrator account:

- **Login URL**: [http://localhost:8000/auth/login](http://localhost:8000/auth/login)
- **Email**: `admin@hrms.local`
- **Password**: `Admin@123`

> [!IMPORTANT]
> Change the default admin password immediately upon first login for production deployments.

---

## 📖 API Documentation

FastAPI automatically generates interactive OpenAPI documentation:

- **Swagger UI (Interactive API Explorer)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI (Clean Specification)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI Schema (JSON)**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## ⌨️ Keyboard Shortcuts & UI Features

| Action | Shortcut | Description |
|---|---|---|
| **Toggle Sidebar Navigation** | `Ctrl + B` / `Cmd + B` | Collapses or expands the navigation sidebar into a compact icon-rail. |
| **Close Modals / Popups** | `Escape` | Dismisses open dialogs, employee roster modals, and dropdown menus. |
| **Staff Roster Lookup** | *Click Card/Pill* | Click any department card or designation pill to inspect assigned employees with search filtering. |

---

## 📄 License

