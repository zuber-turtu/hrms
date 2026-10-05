import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "fallback_secret_key")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours
    _raw_db_url: str = os.getenv("DATABASE_URL", "sqlite:///./hrms.db")
    DATABASE_URL: str = (
        _raw_db_url.replace("postgres://", "postgresql://", 1)
        if _raw_db_url.startswith("postgres://")
        else _raw_db_url
    )

    # Environment settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
    IS_PRODUCTION: bool = ENVIRONMENT in ("production", "prod")

    # Session cookie settings
    COOKIE_NAME: str = "access_token"
    COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")

    # Pluggable Storage settings (local | gdrive | supabase | cloudflare | s3)
    STORAGE_PROVIDER: str = os.getenv("STORAGE_PROVIDER", "local")
    
    # Google Drive
    GDRIVE_SERVICE_ACCOUNT_FILE: str = os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE", "service_account.json")
    GDRIVE_SERVICE_ACCOUNT_JSON: str = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", "")
    GDRIVE_FOLDER_ID: str = os.getenv("GDRIVE_FOLDER_ID", "")
    
    # Supabase Storage
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", ""))
    SUPABASE_BUCKET_NAME: str = os.getenv("SUPABASE_BUCKET_NAME", "hrms-storage")
    
    # AWS S3 / Cloudflare R2 / MinIO
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_PUBLIC_URL_PREFIX: str = os.getenv("S3_PUBLIC_URL_PREFIX", "")
    S3_REGION_NAME: str = os.getenv("S3_REGION_NAME", "auto")

    # Company & Platform Configurations (Configurable dynamically via .env or DB)
    COMPANY_NAME: str = os.getenv("COMPANY_NAME", "Enterprise HRMS")
    COMPANY_TAGLINE: str = os.getenv("COMPANY_TAGLINE", "Personnel & Payroll Platform")
    COMPANY_ADDRESS: str = os.getenv("COMPANY_ADDRESS", "")
    COMPANY_CURRENCY_SYMBOL: str = os.getenv("COMPANY_CURRENCY_SYMBOL", "₹")
    COMPANY_CURRENCY_CODE: str = os.getenv("COMPANY_CURRENCY_CODE", "INR")
    COMPANY_WORKING_DAYS_PER_MONTH: int = int(os.getenv("COMPANY_WORKING_DAYS_PER_MONTH", "22"))
    COMPANY_STANDARD_HOURS_PER_DAY: float = float(os.getenv("COMPANY_STANDARD_HOURS_PER_DAY", "8.0"))
    COMPANY_HALF_DAY_HOURS: float = float(os.getenv("COMPANY_HALF_DAY_HOURS", "4.0"))
    COMPANY_LUNCH_BREAK_HOURS: float = float(os.getenv("COMPANY_LUNCH_BREAK_HOURS", "1.0"))
    COMPANY_LUNCH_START_TIME: str = os.getenv("COMPANY_LUNCH_START_TIME", "13:00")
    COMPANY_LUNCH_END_TIME: str = os.getenv("COMPANY_LUNCH_END_TIME", "14:00")
    APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
    TIMEZONE_OFFSET_MINUTES: int = int(os.getenv("TIMEZONE_OFFSET_MINUTES", "330"))
    APP_COPYRIGHT_YEAR: Optional[int] = (
        int(os.getenv("APP_COPYRIGHT_YEAR")) if os.getenv("APP_COPYRIGHT_YEAR") else None
    )

    # Geofencing Attendance Settings
    GEOFENCE_ENABLED: bool = os.getenv("GEOFENCE_ENABLED", "true").lower() in ("true", "1", "yes")
    GEOFENCE_DEFAULT_LAT: Optional[float] = (
        float(os.getenv("GEOFENCE_DEFAULT_LAT")) if os.getenv("GEOFENCE_DEFAULT_LAT") else None
    )
    GEOFENCE_DEFAULT_LON: Optional[float] = (
        float(os.getenv("GEOFENCE_DEFAULT_LON")) if os.getenv("GEOFENCE_DEFAULT_LON") else None
    )
    GEOFENCE_DEFAULT_RADIUS_METERS: int = int(os.getenv("GEOFENCE_DEFAULT_RADIUS_METERS", "200"))
    GEOFENCE_STRICT_MODE: bool = os.getenv("GEOFENCE_STRICT_MODE", "true").lower() in ("true", "1", "yes")

    # SMTP Email Configuration (Google SMTP / Workspace / SES / SendGrid)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")

    # Application Base URL for link generation
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8000")
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30"))


settings = Settings()
