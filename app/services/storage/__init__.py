import os
import logging
from typing import Optional
from .base import BaseStorageProvider
from .local import LocalStorageProvider
from .gdrive import GoogleDriveStorageProvider
from .s3 import S3StorageProvider
from .supabase import SupabaseStorageProvider

logger = logging.getLogger(__name__)

_storage_instance: Optional[BaseStorageProvider] = None


def get_storage_provider(provider_override: Optional[str] = None) -> BaseStorageProvider:
    """
    Factory function returning the configured Storage Provider.
    Supports 'local', 'gdrive', 'supabase', 'cloudflare', 'r2', 's3', 'aws', 'minio'.
    Falls back gracefully to LocalStorageProvider if cloud provider initialization fails.
    """
    global _storage_instance
    if provider_override is None and _storage_instance is not None:
        return _storage_instance

    from app.config import settings

    provider_name = (
        provider_override
        or getattr(settings, "STORAGE_PROVIDER", None)
        or os.getenv("STORAGE_PROVIDER", "local")
    ).lower()

    instance: Optional[BaseStorageProvider] = None

    if provider_name in ["supabase"]:
        try:
            instance = SupabaseStorageProvider()
            if instance.supabase_url and instance.service_key:
                logger.info("Initialized Supabase Storage Provider")
            else:
                logger.warning("Supabase credentials not configured. Falling back to Local Storage.")
                instance = None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase Storage Provider: {e}. Falling back to Local.")

    elif provider_name == "gdrive":
        try:
            from .gdrive import GoogleDriveStorageProvider

            sa_file = getattr(
                settings,
                "GDRIVE_SERVICE_ACCOUNT_FILE",
                os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE", "service_account.json"),
            )
            sa_json = getattr(
                settings,
                "GDRIVE_SERVICE_ACCOUNT_JSON",
                os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", ""),
            )
            folder_id = getattr(
                settings,
                "GDRIVE_FOLDER_ID",
                os.getenv("GDRIVE_FOLDER_ID", ""),
            )
            if (sa_json and sa_json.strip()) or (sa_file and os.path.exists(sa_file)):
                instance = GoogleDriveStorageProvider(
                    service_account_file=sa_file,
                    service_account_json=sa_json,
                    folder_id=folder_id,
                )
                logger.info("Initialized Google Drive Storage Provider")
            else:
                logger.warning(
                    f"Google Drive credentials not found (file '{sa_file}' missing and GDRIVE_SERVICE_ACCOUNT_JSON not set). Falling back to Local Storage."
                )
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive Provider: {e}. Falling back to Local.")

    elif provider_name in ["s3", "r2", "cloudflare", "aws", "minio"]:
        try:
            bucket = getattr(settings, "S3_BUCKET_NAME", None) or os.getenv("S3_BUCKET_NAME", "")
            if bucket and bucket.strip():
                instance = S3StorageProvider()
                logger.info(f"Initialized S3/Cloudflare ({provider_name}) Storage Provider")
            else:
                logger.warning("S3_BUCKET_NAME not configured. Falling back to Local Storage.")
        except Exception as e:
            logger.error(f"Failed to initialize S3 Provider: {e}. Falling back to Local.")

    if instance is None:
        if getattr(settings, "IS_PRODUCTION", False):
            logger.critical(
                "🚨 CRITICAL STORAGE WARNING: Running in PRODUCTION mode with LocalStorageProvider fallback! "
                "Local disk storage on cloud container/serverless environments (Render, Railway, Fly.io, Heroku) is ephemeral. "
                "Uploaded documents and employee profile photos will be permanently lost when containers restart or redeploy. "
                "Set STORAGE_PROVIDER to 'supabase', 'cloudflare', or 's3' with valid credentials in your production environment variables."
            )
        instance = LocalStorageProvider()

    if provider_override is None:
        _storage_instance = instance

    return instance
