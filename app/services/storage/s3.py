import io
import os
import uuid
from typing import Optional, Tuple
from .base import BaseStorageProvider


class S3StorageProvider(BaseStorageProvider):
    """
    S3 Storage Provider compatible with AWS S3, Cloudflare R2, MinIO, and DigitalOcean Spaces.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        public_url_prefix: Optional[str] = None,
        region_name: Optional[str] = "auto",
    ):
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME", "")
        self.access_key = access_key or os.getenv("S3_ACCESS_KEY_ID", "")
        self.secret_key = secret_key or os.getenv("S3_SECRET_ACCESS_KEY", "")
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL", None)
        self.public_url_prefix = public_url_prefix or os.getenv(
            "S3_PUBLIC_URL_PREFIX", ""
        )
        self.region_name = region_name or os.getenv("S3_REGION_NAME", "auto")
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        import boto3
        from botocore.config import Config

        self._client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            endpoint_url=self.endpoint_url,
            region_name=self.region_name if self.region_name != "auto" else None,
            config=Config(signature_version="s3v4"),
        )
        return self._client

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = "avatars",
    ) -> Tuple[str, Optional[str]]:
        client = self._get_client()

        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg" if "jpeg" in content_type else ".png"

        object_key = f"{folder or 'avatars'}/{uuid.uuid4().hex[:12]}{ext}"

        client.put_object(
            Bucket=self.bucket_name,
            Key=object_key,
            Body=file_bytes,
            ContentType=content_type,
        )

        if self.public_url_prefix:
            prefix = self.public_url_prefix.rstrip("/")
            public_url = f"{prefix}/{object_key}"
        elif self.endpoint_url and "r2.cloudflarestorage.com" in self.endpoint_url:
            public_url = f"https://pub-{self.bucket_name}.r2.dev/{object_key}"
        else:
            public_url = f"https://{self.bucket_name}.s3.amazonaws.com/{object_key}"

        return public_url, object_key

    def delete_file(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        try:
            client = self._get_client()
            client.delete_object(Bucket=self.bucket_name, Key=file_identifier)
            return True
        except Exception:
            return False

    def get_file_bytes(self, file_identifier: str) -> Optional[bytes]:
        if not file_identifier:
            return None
        try:
            client = self._get_client()
            res = client.get_object(Bucket=self.bucket_name, Key=file_identifier)
            return res["Body"].read()
        except Exception:
            return None

    def get_signed_download_url(
        self, file_identifier: str, expires_in_seconds: int = 900
    ) -> Optional[str]:
        if not file_identifier:
            return None
        try:
            client = self._get_client()
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_identifier},
                ExpiresIn=expires_in_seconds,
            )
        except Exception:
            return None

    def file_exists(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        try:
            client = self._get_client()
            client.head_object(Bucket=self.bucket_name, Key=file_identifier)
            return True
        except Exception:
            return False
