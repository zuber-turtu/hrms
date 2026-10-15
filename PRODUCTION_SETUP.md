# 🚀 End-to-End Production Deployment Guide (MySQL + AWS S3)

This guide provides a **step-by-step, zero-to-live production deployment walkthrough** for deploying **Company HRMS** on a Linux Cloud Instance (AWS EC2, DigitalOcean, Hetzner, or GCP) using **MySQL 8.0+** as the relational database and **AWS S3** as the secure document storage engine.

---

## 🏗️ Production Architecture

```mermaid
flowchart TD
    Client["🌐 End-User Browser / Mobile Device"] -->|"HTTPS (Port 443)"| Nginx["🛡️ Nginx Reverse Proxy<br/>(SSL/TLS Termination + Static Caching)"]
    Nginx -->|"Unix Socket / localhost:8000"| Gunicorn["⚡ Gunicorn Master Process<br/>(Uvicorn Multi-Worker Cluster)"]
    
    subgraph AppCluster["FastAPI Application Runtime"]
        Gunicorn --> Worker1["Worker 1 (Async)"]
        Gunicorn --> Worker2["Worker 2 (Async)"]
        Gunicorn --> WorkerN["Worker N (Async)"]
    end
    
    Worker1 & Worker2 & WorkerN -->|"SQLAlchemy Connection Pool"| MySQL[("🗄️ MySQL 8.0+ Database<br/>(utf8mb4 Unicode)")]
    Worker1 & Worker2 & WorkerN -->|"boto3 Secure Streaming / Presigned URLs"| S3[("☁️ AWS S3 Vault<br/>(Private Bucket - KYC & Documents)")]
    Worker1 & Worker2 & WorkerN -->|"Async Cache-Aside"| Redis[("⚡ Redis 7+ Cache")]
    Worker1 & Worker2 & WorkerN -->|"SMTP Port 587"| Email["📧 Email Provider (Gmail / SES)"]
```

---

## 📋 System Requirements & Sizing

| Workload Size | CPU | RAM | Disk Storage | Recommended Cloud Spec |
|:---|:---:|:---:|:---:|:---|
| **50 – 250 Employees** | 2 vCPU | 4 GB | 40 GB NVMe | AWS `t4g.medium` / `t3.medium` |
| **250 – 1,000 Employees** | 4 vCPU | 8 GB | 80 GB NVMe | AWS `t4g.xlarge` / `c6g.xlarge` |
| **1,000+ Employees** | 8 vCPU | 16 GB | 160 GB NVMe | Dedicated App Server + RDS MySQL |

> **Recommended Operating System**: Ubuntu 24.04 LTS or Ubuntu 22.04 LTS (x86_64 or ARM64 / Graviton).

---

## Step 1: Server Preparation & OS Packages

Connect to your server via SSH:
```bash
ssh -i your-key.pem ubuntu@your-server-ip
```

Update system packages and install Python 3.12, Nginx, Git, and build tools:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl ufw \
    build-essential libssl-dev libffi-dev nginx certbot python3-certbot-nginx \
    pkg-config default-libmysqlclient-dev
```

### Configure Firewall (UFW)
```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (Certbot & Redirection)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw --force enable
sudo ufw status
```

---

## Step 2: Install & Harden MySQL 8.0

### 2.1 Install MySQL Server
```bash
sudo apt install -y mysql-server
sudo systemctl enable mysql
sudo systemctl start mysql
```

### 2.2 Secure MySQL Installation
Run the automated security script:
```bash
sudo mysql_secure_installation
```
- Validate Password Component: **Yes** (select Level 1 or 2).
- Remove anonymous users: **Yes**.
- Disallow root login remotely: **Yes**.
- Remove test database: **Yes**.
- Reload privilege tables: **Yes**.

### 2.3 Create Production Database & Dedicated User
Log in to MySQL as root:
```bash
sudo mysql
```

Execute the following SQL commands:
```sql
-- 1. Create database with full UTF-8 Unicode support
CREATE DATABASE hrms_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. Create a dedicated application user with a strong password
CREATE USER 'hrms_user'@'localhost' IDENTIFIED BY 'PutYourVeryStrongPasswordHere!2026';

-- 3. Grant full privileges on the HRMS database
GRANT ALL PRIVILEGES ON hrms_db.* TO 'hrms_user'@'localhost';
FLUSH PRIVILEGES;

-- 4. Verify database creation
SHOW DATABASES;
EXIT;
```

### 2.4 Optimize MySQL for Concurrency
Edit MySQL configuration:
```bash
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf
```
Add or adjust these settings under the `[mysqld]` block:
```ini
[mysqld]
# Full Unicode Everywhere (Emoji & International Names)
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

# InnoDB Buffer Pool (Allocate 50-60% of total server RAM, e.g., 2G on a 4GB RAM server)
innodb_buffer_pool_size = 2G
innodb_log_file_size = 512M
innodb_flush_log_at_trx_commit = 2
innodb_file_per_table = 1

# Connection Capacity
max_connections = 250
wait_timeout = 600
interactive_timeout = 600
```
Restart MySQL to apply optimizations:
```bash
sudo systemctl restart mysql
```

---

## Step 3: Provision AWS S3 Private Vault & IAM

### 3.1 Create S3 Bucket
1. Log in to the [AWS Management Console](https://console.aws.amazon.com/s3/).
2. Click **Create bucket**.
3. **Bucket name**: e.g. `yourcompany-hrms-vault` (must be globally unique).
4. **AWS Region**: Select the region closest to your workforce (e.g. `ap-south-1` for India / Mumbai).
5. **Block Public Access settings for this bucket**:
   - Keep **"Block all public access"** checked **ON** (Enabled).
   > [!IMPORTANT]
   > Our HRMS streams documents securely through authenticated endpoints and generates time-limited 15-minute presigned download URLs. The bucket itself must remain strictly private!
6. Click **Create bucket**.

### 3.2 Create IAM User & Access Policy
1. In the AWS Console, open **IAM** → **Users** → **Create user**.
2. **User name**: `hrms-s3-service-worker`.
3. Under **Permissions options**, select **Attach policies directly** → **Create policy**.
4. Switch to the **JSON** tab and paste:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "HRMSPrivateBucketAccess",
               "Effect": "Allow",
               "Action": [
                   "s3:PutObject",
                   "s3:GetObject",
                   "s3:DeleteObject",
                   "s3:HeadObject"
               ],
               "Resource": "arn:aws:s3:::yourcompany-hrms-vault/*"
           },
           {
               "Sid": "HRMSBucketListAccess",
               "Effect": "Allow",
               "Action": [
                   "s3:ListBucket"
               ],
               "Resource": "arn:aws:s3:::yourcompany-hrms-vault"
           }
       ]
   }
   ```
   *(Replace `yourcompany-hrms-vault` with your actual bucket name).*
5. Name the policy `HRMS_S3_Storage_Policy` and click **Create policy**.
6. Attach this policy to the `hrms-s3-service-worker` user.
7. Open the user, go to **Security credentials** → **Create access key** (Application running outside AWS).
8. Save the **Access Key ID** (`AKIA...`) and **Secret Access Key**.

---

## Step 4: Clone Application & Configure Python Environment

### 4.1 Create System Service User & Directory
```bash
# Create dedicated system user
sudo useradd -m -d /var/www/hrms -s /bin/bash hrms
sudo usermod -aG www-data hrms

# Clone repository
sudo git clone https://github.com/your-org/hrms.git /var/www/hrms
cd /var/www/hrms
```

### 4.2 Set Up Virtual Environment & Dependencies
```bash
sudo chown -R hrms:www-data /var/www/hrms
sudo -u hrms python3 -m venv /var/www/hrms/venv
sudo -u hrms /var/www/hrms/venv/bin/pip install --upgrade pip
sudo -u hrms /var/www/hrms/venv/bin/pip install -r /var/www/hrms/requirements.txt
```

---

## Step 5: Configure Production Environment (`.env`)

Create the production `.env` file:
```bash
sudo -u hrms nano /var/www/hrms/.env
```

Paste and customize the following production configuration:

```ini
# ==============================================================================
# TURTU HRMS - PRODUCTION CONFIGURATION
# ==============================================================================

ENVIRONMENT=production
IS_PRODUCTION=true

# 1. Generate strong secret key: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=paste_your_generated_64_character_hex_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# Cookie Security (Auto-enforced to secure HTTPS cookies in production)
COOKIE_NAME=access_token
COOKIE_SAMESITE=lax
COOKIE_SECURE=true

# 2. MySQL Production Database Connection String
DATABASE_URL=mysql://hrms_user:PutYourVeryStrongPasswordHere!2026@localhost:3306/hrms_db

# 3. AWS S3 Cloud Storage Engine
STORAGE_PROVIDER=s3
S3_BUCKET_NAME=yourcompany-hrms-vault
S3_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
S3_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
S3_REGION_NAME=ap-south-1

# 4. Email / SMTP Configuration (Password resets, notifications, security alerts)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-hr-email@yourcompany.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-hr-email@yourcompany.com
SMTP_FROM_NAME="TURTU HRMS"
SMTP_USE_TLS=True

# Base URL (Must match your live domain)
APP_BASE_URL=https://hrms.yourcompany.com
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30

# 5. Connection Pooling
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=15
DB_POOL_RECYCLE=1800
DB_POOL_PRE_PING=true
DB_POOL_TIMEOUT=30

# 6. Organization Defaults
COMPANY_NAME="TURTU INDIA LLP"
COMPANY_CURRENCY_SYMBOL="₹"
COMPANY_CURRENCY_CODE="INR"
TIMEZONE_OFFSET_MINUTES=330
APP_TIMEZONE="IST"
```

Lock down file permissions so only `hrms` user can read credentials:
```bash
sudo chmod 600 /var/www/hrms/.env
sudo chown hrms:hrms /var/www/hrms/.env
```

---

## Step 6: Configure Systemd Service Manager

Create a persistent background systemd service:
```bash
sudo nano /etc/systemd/system/hrms.service
```

Paste the following service definition:
```ini
[Unit]
Description=Turtu HRMS Enterprise Application (Gunicorn + Uvicorn)
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=notify
User=hrms
Group=www-data
WorkingDirectory=/var/www/hrms
EnvironmentFile=/var/www/hrms/.env
ExecStart=/var/www/hrms/venv/bin/gunicorn -c /var/www/hrms/gunicorn_conf.py main:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=always
RestartSec=5

# Sandboxing & Security
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

### Start & Enable Service
```bash
sudo systemctl daemon-reload
sudo systemctl start hrms
sudo systemctl enable hrms
sudo systemctl status hrms
```

---

## Step 7: Configure Nginx & Let's Encrypt SSL

### 7.1 Create Nginx Site Configuration
```bash
sudo nano /etc/nginx/sites-available/hrms
```

Paste the following Nginx virtual host configuration:
```nginx
# Rate Limiting Zone
limit_req_zone $binary_remote_addr zone=hrms_limit:10m rate=30r/s;

server {
    listen 80;
    server_name hrms.yourcompany.com;

    # Maximum upload size for employee documents & avatars (50MB)
    client_max_body_size 50M;

    # Logging
    access_log /var/log/nginx/hrms_access.log;
    error_log /var/log/nginx/hrms_error.log;

    # Static Assets Direct Serving & Browser Caching
    location /static/ {
        alias /var/www/hrms/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
        access_log off;
    }

    # Proxy to Gunicorn ASGI Cluster
    location / {
        limit_req zone=hrms_limit burst=50 nodelay;

        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for bulk payslip generation & Excel exports
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
```

### 7.2 Enable Site & Test Configuration
```bash
sudo ln -sf /etc/nginx/sites-available/hrms /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 7.3 Install Free SSL Certificate via Certbot
```bash
sudo certbot --nginx -d hrms.yourcompany.com
```
*Select option to automatically redirect all HTTP traffic to HTTPS.*

Certbot sets up an auto-renewing cron job. Test the renewal with:
```bash
sudo certbot renew --dry-run
```

---

## Step 8: Post-Deployment Verification & First Login

### 8.1 Check Health Endpoint
Open in browser or terminal:
```bash
curl -I https://hrms.yourcompany.com/health
```
Expected output:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-10-14T14:00:00.000000",
  "environment": "production"
}
```

### 8.2 First Login & Password Rotation
1. Navigate to: `https://hrms.yourcompany.com/login`
2. Log in using initial super-admin credentials:
   - **Email**: `admin@hrms.local`
   - **Password**: `Admin@123`
3. Go to **My Profile** or **Company Settings** and **change the password immediately**.
   > [!NOTE]
   > Changing your password increments your account's `token_version`, immediately invalidating all prior sessions across devices.

### 8.3 Verify Document Upload to AWS S3
1. Navigate to **Employees** → Select any employee → **Documents**.
2. Upload a sample document (PDF or image).
3. Confirm the upload completes and click **View**.
4. Log into your **AWS S3 Console** and confirm the document appears in the `documents/` folder.

---

## Step 9: Automated Maintenance & Backups

### 9.1 Automated Daily MySQL Backups
Create backup directory and script:
```bash
sudo mkdir -p /var/backups/hrms_mysql
sudo nano /usr/local/bin/backup_hrms_mysql.sh
```

Paste:
```bash
#!/bin/bash
BACKUP_DIR="/var/backups/hrms_mysql"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/hrms_db_$TIMESTAMP.sql.gz"

# Create compressed dump
mysqldump -u hrms_user -p'PutYourVeryStrongPasswordHere!2026' --single-transaction --quick hrms_db | gzip > "$BACKUP_FILE"

# Keep last 14 days of backups only
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete
```

Make executable and add to crontab:
```bash
sudo chmod +x /usr/local/bin/backup_hrms_mysql.sh

# Run every night at 2:00 AM
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup_hrms_mysql.sh") | crontab -
```

### 9.2 Zero-Downtime Rolling Application Updates
When pulling updates from GitHub to your live production server:
```bash
cd /var/www/hrms

# 1. Pull the latest commits
sudo -u hrms git pull origin main

# 2. Update dependencies (if requirements.txt changed)
sudo -u hrms /var/www/hrms/venv/bin/pip install -r requirements.txt

# 3. Apply all pending database schema migrations
sudo -u hrms /var/www/hrms/venv/bin/python migrations/run_migrations.py

# 4. Perform seamless Gunicorn rolling reload (zero dropped connections)
sudo systemctl reload hrms
```

---

## 🔍 Useful Diagnostic Commands

```bash
# View live application logs
sudo journalctl -u hrms -f

# View Nginx access & error logs
sudo tail -f /var/log/nginx/hrms_access.log
sudo tail -f /var/log/nginx/hrms_error.log

# Check MySQL connection status
mysqladmin -u hrms_user -p status

# Test S3 connectivity from server
/var/www/hrms/venv/bin/python -c "import boto3; s3 = boto3.client('s3'); print('S3 OK')"
```
