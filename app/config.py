import os
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


settings = Settings()
