# 🚀 Turtu HRMS — Complete Setup & Deployment Guide

Welcome to **Turtu HRMS**, an enterprise-grade Personnel, Payroll, Attendance, and Document Management platform built with FastAPI, SQLAlchemy 2.0, MySQL / PostgreSQL / SQLite, Jinja2, HTMX, and Tailwind CSS.

This guide provides step-by-step instructions for:
- [1. Prerequisites](#1-prerequisites)
- [2. Local Development Setup (Windows / macOS / Linux)](#2-local-development-setup)
- [3. Production Cloud Instance Deployment (Ubuntu / Debian / EC2 / Droplets)](#3-production-cloud-instance-deployment)
- [4. Database Setup & Configuration (MySQL Preferred, PostgreSQL, SQLite)](#4-database-setup--configuration)
  - [Option A: MySQL 8.0 / MariaDB (Preferred Enterprise Choice)](#option-a-mysql-80--mariadb-preferred-enterprise-choice)
  - [Option B: PostgreSQL / Supabase](#option-b-postgresql--supabase)
  - [Option C: SQLite (Local & Development Only)](#option-c-sqlite-local--development-only)
- [5. Docker & Containerized Deployment (MySQL + Gunicorn)](#5-docker--containerized-deployment)
- [6. Environment Configuration Reference (`.env`)](#6-environment-configuration-reference-env)
- [7. Pluggable Cloud Storage Setup (S3, Cloudflare R2, Supabase, GDrive)](#7-pluggable-cloud-storage-setup)
- [8. Zero-Downtime Updates, Maintenance & Backups](#8-zero-downtime-updates-maintenance--backups)
- [9. Troubleshooting & Health Checks](#9-troubleshooting--health-checks)

---

## 1. Prerequisites

Ensure your system or cloud instance meets the following minimum requirements:

| Component | Minimum Specification | Recommended (Production) |
| :--- | :--- | :--- |
| **Operating System** | Ubuntu 22.04 / 24.04 LTS, Debian 12, macOS, Windows 10/11 | Ubuntu 24.04 LTS (x86_64 / ARM64) |
| **Python** | Python 3.11 or 3.12 | Python 3.12 |
| **Memory (RAM)** | 2 GB | 4 GB to 8 GB |
| **CPU** | 1 vCPU | 2 to 4 vCPUs |
| **Primary Database** | **MySQL 8.0+ / MariaDB 10.6+ (Recommended)** | Managed MySQL 8.0 / AWS RDS MySQL |
| **Alternative DBs** | PostgreSQL 14+ / Supabase or SQLite 3 (Dev only) | PostgreSQL 16 / Supabase Pooler |
| **Web Server** | Uvicorn (Dev) | Nginx + Gunicorn (Uvicorn Worker Cluster) |

---

## 2. Local Development Setup

### Step 2.1: Clone the Repository
```bash
git clone https://github.com/your-org/hrms.git
cd hrms
```

### Step 2.2: Create and Activate Virtual Environment
**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 2.3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.4: Configure Environment Variables
Copy the example environment file:
```bash
cp .env.example .env
```
*(On Windows: `copy .env.example .env`)*

Open `.env` in your editor and configure your database:
```ini
# Option 1: MySQL (Preferred)
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/hrms_db

# Option 2: SQLite (Instant zero-config start for local evaluation)
# DATABASE_URL=sqlite:///./hrms.db
```

### Step 2.5: Start Development Server
```bash
uvicorn main:app --reload --port 8000
```
Visit **[http://localhost:8000](http://localhost:8000)** in your browser.

> **Default Super Admin Credentials** (automatically seeded on first start):
> - **Email**: `admin@turtu.com`
> - **Password**: `admin123`
> *(⚠️ Make sure to change this default password in Company Settings immediately!)*

---

## 3. Production Cloud Instance Deployment

Follow this guide to deploy on an **AWS EC2 instance, DigitalOcean Droplet, GCP Compute VM, or Hetzner server** running Ubuntu/Debian.

```
Internet (HTTPS) 
      │
      ▼
   [Nginx] (Port 80/443: SSL, Gzip, Static Asset Cache)
      │
      ▼ (Reverse Proxy to 127.0.0.1:8000)
  [Gunicorn] (Multi-Worker Master Process)
      ├─► [Uvicorn Worker 1]
      ├─► [Uvicorn Worker 2]
      ├─► [Uvicorn Worker 3]
      └─► [Uvicorn Worker 4]
            │
            ▼
     [MySQL 8.0 / MariaDB Database (InnoDB UTF8mb4)]
```

### Step 3.1: System Package Installation
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx default-libmysqlclient-dev pkg-config libpq-dev curl
```

### Step 3.2: Clone Project to `/var/www/hrms`
```bash
sudo mkdir -p /var/www/hrms
sudo chown -R $USER:$USER /var/www/hrms
git clone https://github.com/your-org/hrms.git /var/www/hrms
cd /var/www/hrms
```

### Step 3.3: Set Up Python Virtualenv
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3.4: Configure Production `.env`
```bash
cp .env.example .env
nano .env
```
Set production settings:
```ini
ENVIRONMENT=production
SECRET_KEY=generate_with_openssl_rand_hex_32
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# Database: MySQL (Recommended)
DATABASE_URL=mysql+pymysql://hrms_user:YourStrongPassword123!@localhost:3306/hrms_db

# Pluggable Storage (local, s3, supabase, cloudflare, gdrive)
STORAGE_PROVIDER=local
```

Generate a secure secret key:
```bash
openssl rand -hex 32
```

---

### Step 3.5: Configure Systemd Service (Auto-Start & Crash Recovery)
We have prepared a production systemd unit in `deploy/hrms.service`.

1. Copy service file:
   ```bash
   sudo cp deploy/hrms.service /etc/systemd/system/hrms.service
   ```

2. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable hrms
   sudo systemctl start hrms
   ```

3. Check running status:
   ```bash
   sudo systemctl status hrms
   ```

---

### Step 3.6: Configure Nginx Reverse Proxy & SSL

1. Copy Nginx site configuration:
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/hrms
   ```

2. Replace `hrms.yourdomain.com` with your actual domain:
   ```bash
   sudo sed -i 's/hrms.yourdomain.com/your-actual-domain.com/g' /etc/nginx/sites-available/hrms
   ```

3. Enable the site and test configuration:
   ```bash
   sudo ln -s /etc/nginx/sites-available/hrms /etc/nginx/sites-enabled/
   sudo nginx -t
   ```

4. Obtain Free Let's Encrypt SSL Certificate:
   ```bash
   sudo certbot --nginx -d your-actual-domain.com
   ```

5. Restart Nginx:
   ```bash
   sudo systemctl restart nginx
   ```

---

## 4. Database Setup & Configuration

### Option A: MySQL 8.0 / MariaDB (Preferred Enterprise Choice)

MySQL is the **primary recommended database** for high-volume attendance punches, bulk payslip generation, and concurrent payroll runs.

#### 1. Install MySQL Server (Ubuntu/Debian)
```bash
sudo apt install -y mysql-server
sudo systemctl enable mysql
sudo systemctl start mysql
```

#### 2. Create Database & Dedicated User
Log in to MySQL root:
```bash
sudo mysql
```
Execute the following SQL commands:
```sql
-- 1. Create database with full UTF-8 (Emoji & International names support)
CREATE DATABASE hrms_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. Create dedicated user
CREATE USER 'hrms_user'@'localhost' IDENTIFIED BY 'YourStrongPassword123!';

-- 3. Grant full privileges
GRANT ALL PRIVILEGES ON hrms_db.* TO 'hrms_user'@'localhost';
FLUSH PRIVILEGES;

-- 4. Verify and exit
SHOW DATABASES;
EXIT;
```

#### 3. Update `.env`
```ini
DATABASE_URL=mysql+pymysql://hrms_user:YourStrongPassword123!@localhost:3306/hrms_db
```

#### 4. MySQL Performance Tuning (`/etc/mysql/mysql.conf.d/mysqld.cnf`)
For high concurrency (500+ employees punching simultaneously):
```ini
[mysqld]
# Enable UTF-8 Everywhere
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

# Memory & Buffer Pool (Set to 50-70% of available server RAM)
innodb_buffer_pool_size = 2G
innodb_log_file_size = 512M
innodb_flush_log_at_trx_commit = 2
innodb_file_per_table = 1

# Connection Handling
max_connections = 250
wait_timeout = 600
interactive_timeout = 600
```
Restart MySQL to apply:
```bash
sudo systemctl restart mysql
```

---

### Option B: PostgreSQL / Supabase

If your organization standardizes on PostgreSQL:

#### 1. Install PostgreSQL
```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

#### 2. Create Database & User
```bash
sudo -u postgres psql
```
In the PostgreSQL prompt:
```sql
CREATE DATABASE hrms_db;
CREATE USER hrms_user WITH ENCRYPTED PASSWORD 'YourStrongPassword123!';
GRANT ALL PRIVILEGES ON DATABASE hrms_db TO hrms_user;
ALTER DATABASE hrms_db OWNER TO hrms_user;
\q
```

#### 3. Update `.env`
```ini
DATABASE_URL=postgresql://hrms_user:YourStrongPassword123!@localhost:5432/hrms_db
```

---

### Option C: SQLite (Local & Development Only)

For instant evaluation with zero setup:
```ini
DATABASE_URL=sqlite:///./hrms.db
```
> ⚠️ **Note**: SQLite uses file-level locking during writes. For multi-user concurrent attendance check-ins, always use **MySQL** or **PostgreSQL** in production.

---

## 5. Docker & Containerized Deployment

We provide a production `docker-compose.yml` pre-configured with **MySQL 8.0** and **Gunicorn multi-worker web app**.

### Step 5.1: Launch Stack
```bash
cd /var/www/hrms
docker compose -f deploy/docker-compose.yml up -d --build
```

### Step 5.2: Manage Containers
```bash
# Check status
docker compose -f deploy/docker-compose.yml ps

# View real-time logs
docker compose -f deploy/docker-compose.yml logs -f hrms-web

# Stop stack
docker compose -f deploy/docker-compose.yml down
```

---

## 6. Environment Configuration Reference (`.env`)

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Set to `production` in live environments. |
| `SECRET_KEY` | *(Random Hex)* | JWT token signing key (`openssl rand -hex 32`). |
| `DATABASE_URL` | `mysql+pymysql://...` | **Primary**: MySQL (`mysql+pymysql://user:pass@host:3306/db`). Also supports PostgreSQL & SQLite. |
| `COOKIE_SECURE` | `true` | Enforces HTTPS-only cookies in production. |
| `COOKIE_SAMESITE` | `lax` | Browser CSRF protection policy (`lax` or `strict`). |
| `STORAGE_PROVIDER` | `local` | `local`, `s3`, `supabase`, `gdrive`, or `cloudflare`. |
| `S3_BUCKET_NAME` | `""` | AWS S3 / Cloudflare R2 bucket name. |
| `S3_ACCESS_KEY_ID` | `""` | S3 Access Key ID. |
| `S3_SECRET_ACCESS_KEY` | `""` | S3 Secret Access Key. |
| `S3_REGION_NAME` | `auto` | AWS Region (e.g. `ap-south-1`). |
| `SUPABASE_URL` | `""` | Supabase Project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | Supabase Service Role Key. |
| `COMPANY_NAME` | `TURTU INDIA LLP` | Organization display name. |
| `COMPANY_CURRENCY_SYMBOL` | `₹` | Currency symbol displayed on payslips & salary tables. |
| `COMPANY_CURRENCY_CODE` | `INR` | Currency code (`INR`, `USD`, `AED`, `EUR`, etc.). |

---

## 7. Pluggable Cloud Storage Setup

To ensure documents and payslips persist safely even if the server is rebuilt, choose a cloud storage provider in `.env`:

### Option 1: AWS S3 / MinIO
```ini
STORAGE_PROVIDER=s3
S3_BUCKET_NAME=hrms-production-vault
S3_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
S3_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
S3_REGION_NAME=ap-south-1
```

### Option 2: Cloudflare R2 (Zero Egress Fees)
```ini
STORAGE_PROVIDER=cloudflare
S3_BUCKET_NAME=hrms-storage
S3_ACCESS_KEY_ID=your_r2_access_key_id
S3_SECRET_ACCESS_KEY=your_r2_secret_access_key
S3_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
S3_PUBLIC_URL_PREFIX=https://cdn.yourcompany.com
S3_REGION_NAME=auto
```

### Option 3: Supabase Storage
```ini
STORAGE_PROVIDER=supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
SUPABASE_BUCKET_NAME=hrms-storage
```

---

## 8. Zero-Downtime Updates, Maintenance & Backups

### Zero-Downtime Code Updates
When pulling updates from Git without dropping active user connections:
```bash
cd /var/www/hrms
git pull origin main
source venv/bin/activate
pip install -r requirements.txt

# Perform zero-downtime worker reload (Gunicorn SIGHUP)
sudo systemctl reload hrms
```

### Automated MySQL Database Backups
Set up a daily cron backup:
```bash
crontab -e
```
Add the following line to back up MySQL every night at 2:00 AM:
```cron
0 2 * * * mysqldump -u hrms_user -p'YourStrongPassword123!' hrms_db | gzip > /var/backups/hrms_mysql_$(date +\%Y\%m\%d).sql.gz
```

---

## 9. Troubleshooting & Health Checks

### Check Application Health API:
```bash
curl http://127.0.0.1:8000/api/v1/health
```
Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-10-07T12:00:00.000000",
  "environment": "production"
}
```

### View Live Application Logs:
```bash
# View systemd service logs
sudo journalctl -u hrms -f

# View Nginx access & error logs
sudo tail -f /var/log/nginx/error.log
```

### Common Issues & Solutions:

1. **MySQL Access Denied Error:**
   - Verify username, password, and host in `DATABASE_URL`.
   - Test directly via command line: `mysql -u hrms_user -p -h localhost hrms_db`.

2. **Nginx 502 Bad Gateway:**
   - Verify Gunicorn is running: `sudo systemctl status hrms`.
   - Verify Gunicorn is bound to `127.0.0.1:8000`.

3. **Port 8000 in use:**
   ```bash
   sudo lsof -i :8000
   sudo kill -9 <PID>
   ```

---

## 🤝 Support & Enterprise Architecture

For questions or customized enterprise workflows, refer to the [PROJECT_SPEC.md](PROJECT_SPEC.md) or submit an issue in the repository.
