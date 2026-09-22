import os
import uuid
import logging
from typing import Optional, Tuple
import urllib.parse
from .base import BaseStorageProvider

logger = logging.getLogger(__name__)


class SupabaseStorageProvider(BaseStorageProvider):
    """
    Supabase Storage Provider using Supabase REST Storage API & S3 compatibility.
    Integrates directly with your Supabase project (e.g. gphyjvlcqbfdhxfynqil).
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_key: Optional[str] = None,
        bucket_avatars: Optional[str] = None,
        bucket_docs: Optional[str] = None,
    ):
        self.supabase_url = (
            supabase_url
            or os.getenv("SUPABASE_URL", "")
        ).rstrip("/")
        
        # If url not explicitly set, deduce from DATABASE_URL if available
        if not self.supabase_url:
            db_url = os.getenv("DATABASE_URL", "")
            if "supabase.com" in db_url or "supabase.co" in db_url:
                # e.g. postgres.gphyjvlcqbfdhxfynqil... -> https://gphyjvlcqbfdhxfynqil.supabase.co
                try:
                    parts = db_url.split("@")[0].split(":")[-1]
                    if "." in parts:
                        ref = parts.split(".")[1]
                        self.supabase_url = f"https://{ref}.supabase.co"
                except Exception:
                    pass

        self.service_key = (
            service_key
            or os.getenv("SUPABASE_SERVICE_KEY")
            or os.getenv("SUPABASE_KEY", "")
        )
        self.bucket_avatars = bucket_avatars or os.getenv("SUPABASE_BUCKET_AVATARS", "hrms-avatars")
        self.bucket_docs = bucket_docs or os.getenv("SUPABASE_BUCKET_DOCS", "hrms-documents")

    def _get_headers(self, content_type: str = "application/octet-stream"):
        return {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
            "Content-Type": content_type,
        }

    def _ensure_bucket(self, bucket_name: str, is_public: bool = True):
        """Creates bucket if it does not exist."""
        if not self.supabase_url or not self.service_key:
            return
        import httpx
        try:
            url = f"{self.supabase_url}/storage/v1/bucket"
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    url,
                    headers=self._get_headers("application/json"),
                    json={"id": bucket_name, "name": bucket_name, "public": is_public},
                )
        except Exception:
            pass

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = "avatars",
    ) -> Tuple[str, Optional[str]]:
        import httpx

        if not self.supabase_url or not self.service_key:
            raise ValueError("Supabase URL and Service Key must be configured.")

        bucket = self.bucket_avatars if folder == "avatars" else self.bucket_docs
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg" if "jpeg" in content_type else ".png"

        unique_filename = f"{uuid.uuid4().hex[:12]}{ext}"
        storage_path = f"{folder or 'misc'}/{unique_filename}"

        upload_url = f"{self.supabase_url}/storage/v1/object/{bucket}/{storage_path}"
        headers = self._get_headers(content_type)
        headers["x-upsert"] = "true"

        with httpx.Client(timeout=30.0) as client:
            res = client.post(upload_url, headers=headers, content=file_bytes)
            if res.status_code not in (200, 201):
                # If bucket not found, try creating it and retry
                self._ensure_bucket(bucket, is_public=(bucket == self.bucket_avatars))
                res = client.post(upload_url, headers=headers, content=file_bytes)
                if res.status_code not in (200, 201):
                    raise RuntimeError(f"Supabase upload failed: {res.text}")

        # Construct public or relative URL
        public_url = f"{self.supabase_url}/storage/v1/object/public/{bucket}/{storage_path}"
        return public_url, f"{bucket}/{storage_path}"

    def delete_file(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        import httpx
        try:
            clean_id = file_identifier
            if "storage/v1/object/public/" in clean_id:
                clean_id = clean_id.split("storage/v1/object/public/")[-1]

            parts = clean_id.split("/", 1)
            bucket = parts[0] if len(parts) > 1 else self.bucket_avatars
            path = parts[1] if len(parts) > 1 else clean_id

            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{path}"
            with httpx.Client(timeout=10.0) as client:
                res = client.delete(url, headers=self._get_headers())
                return res.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Supabase delete failed: {e}")
            return False

    def get_file_bytes(self, file_identifier: str) -> Optional[bytes]:
        if not file_identifier:
            return None
        import httpx
        try:
            clean_id = file_identifier
            if "storage/v1/object/" in clean_id:
                clean_id = clean_id.split("storage/v1/object/")[-1].replace("public/", "").replace("authenticated/", "")

            parts = clean_id.split("/", 1)
            bucket = parts[0] if len(parts) > 1 else self.bucket_docs
            path = parts[1] if len(parts) > 1 else clean_id

            url = f"{self.supabase_url}/storage/v1/object/authenticated/{bucket}/{path}"
            with httpx.Client(timeout=30.0) as client:
                res = client.get(url, headers=self._get_headers())
                if res.status_code == 200:
                    return res.content
                
                # Try public endpoint
                pub_url = f"{self.supabase_url}/storage/v1/object/public/{bucket}/{path}"
                res_pub = client.get(pub_url)
                if res_pub.status_code == 200:
                    return res_pub.content
        except Exception as e:
            logger.warning(f"Supabase get_file_bytes error: {e}")
        return None

    def get_signed_download_url(
        self, file_identifier: str, expires_in_seconds: int = 900
    ) -> Optional[str]:
        if not file_identifier:
            return None
        import httpx
        try:
            clean_id = file_identifier
            if "storage/v1/object/" in clean_id:
                clean_id = clean_id.split("storage/v1/object/")[-1].replace("public/", "").replace("authenticated/", "")

            parts = clean_id.split("/", 1)
            bucket = parts[0] if len(parts) > 1 else self.bucket_docs
            path = parts[1] if len(parts) > 1 else clean_id

            sign_url = f"{self.supabase_url}/storage/v1/object/sign/{bucket}/{path}"
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    sign_url,
                    headers=self._get_headers("application/json"),
                    json={"expiresIn": expires_in_seconds},
                )
                if res.status_code == 200:
                    data = res.json()
                    signed_path = data.get("signedURL")
                    return f"{self.supabase_url}{signed_path}"
        except Exception as e:
            logger.warning(f"Supabase get_signed_download_url error: {e}")
        return None

    def file_exists(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        import httpx
        try:
            clean_id = file_identifier
            if "storage/v1/object/" in clean_id:
                clean_id = clean_id.split("storage/v1/object/")[-1].replace("public/", "").replace("authenticated/", "")

            parts = clean_id.split("/", 1)
            bucket = parts[0] if len(parts) > 1 else self.bucket_docs
            path = parts[1] if len(parts) > 1 else clean_id

            url = f"{self.supabase_url}/storage/v1/object/info/{bucket}/{path}"
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url, headers=self._get_headers())
                if res.status_code == 200:
                    return True
                # Fallback to public check
                pub_url = f"{self.supabase_url}/storage/v1/object/public/{bucket}/{path}"
                res_head = client.head(pub_url)
                return res_head.status_code == 200
        except Exception:
            return False
