import os
import uuid
from typing import Optional, Tuple
from .base import BaseStorageProvider


class LocalStorageProvider(BaseStorageProvider):
    """
    Local filesystem storage provider:
    - Public assets (avatars, icons) are saved to static/uploads/avatars/
    - Confidential documents (KYC, contracts, etc.) are isolated in storage/private_documents/
      and are NEVER accessible through public static mounts.
    """

    def __init__(
        self,
        base_upload_dir: str = "static/uploads",
        private_upload_dir: str = "storage/private_documents",
    ):
        self.base_upload_dir = os.path.abspath(base_upload_dir)
        self.private_upload_dir = os.path.abspath(private_upload_dir)
        os.makedirs(self.base_upload_dir, exist_ok=True)
        os.makedirs(self.private_upload_dir, exist_ok=True)

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = "avatars",
    ) -> Tuple[str, Optional[str]]:
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg" if "jpeg" in content_type else ".png"

        unique_filename = f"{uuid.uuid4().hex[:12]}{ext}"
        is_private = (folder or "").strip().lower() in ("documents", "private", "kyc")

        if is_private:
            target_dir = self.private_upload_dir
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, unique_filename)
            relative_url = f"private://documents/{unique_filename}"
        else:
            target_dir = os.path.join(self.base_upload_dir, folder or "misc")
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, unique_filename)
            relative_url = f"/static/uploads/{folder or 'misc'}/{unique_filename}"

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return relative_url, unique_filename

    def _is_safe_path(self, file_path: str) -> bool:
        """Defense-in-depth against directory traversal attacks."""
        resolved = os.path.abspath(file_path)
        return resolved.startswith(self.base_upload_dir) or resolved.startswith(self.private_upload_dir)

    def _resolve_local_path(self, file_identifier: str) -> Optional[str]:
        if not file_identifier:
            return None

        file_identifier_clean = str(file_identifier).strip()

        # Case 1: Private scheme
        if file_identifier_clean.startswith("private://documents/"):
            base_name = file_identifier_clean.replace("private://documents/", "").lstrip("/\\")
            file_path = os.path.join(self.private_upload_dir, base_name)
        elif file_identifier_clean.startswith("private://"):
            base_name = file_identifier_clean.replace("private://", "").lstrip("/\\")
            file_path = os.path.join(self.private_upload_dir, base_name)
        # Case 2: Legacy or static URL path
        elif file_identifier_clean.startswith("/static/uploads/documents/"):
            base_name = file_identifier_clean.replace("/static/uploads/documents/", "").lstrip("/\\")
            # First check private storage, fallback to static if not yet moved
            file_path = os.path.join(self.private_upload_dir, base_name)
            if not os.path.exists(file_path):
                file_path = os.path.join(self.base_upload_dir, "documents", base_name)
        elif file_identifier_clean.startswith("/static/uploads/"):
            clean_rel = file_identifier_clean.replace("/static/uploads/", "").lstrip("/\\")
            file_path = os.path.join(self.base_upload_dir, clean_rel)
        elif "/" in file_identifier_clean or "\\" in file_identifier_clean:
            base_name = os.path.basename(file_identifier_clean)
            file_path = os.path.join(self.private_upload_dir, base_name)
            if not os.path.exists(file_path):
                file_path = os.path.join(self.base_upload_dir, file_identifier_clean.lstrip("/\\"))
        else:
            base_name = os.path.basename(file_identifier_clean)
            file_path = os.path.join(self.private_upload_dir, base_name)
            if not os.path.exists(file_path):
                file_path = os.path.join(self.base_upload_dir, "documents", base_name)
            if not os.path.exists(file_path):
                file_path = os.path.join(self.base_upload_dir, "avatars", base_name)

        if not self._is_safe_path(file_path):
            return None
        return file_path

    def file_exists(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        file_path = self._resolve_local_path(file_identifier)
        return bool(file_path and os.path.exists(file_path) and os.path.isfile(file_path))

    def delete_file(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        file_path = self._resolve_local_path(file_identifier)
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except Exception:
                return False
        return False

    def get_file_bytes(self, file_identifier: str) -> Optional[bytes]:
        if not file_identifier:
            return None
        file_path = self._resolve_local_path(file_identifier)
        if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
            try:
                with open(file_path, "rb") as f:
                    return f.read()
            except Exception:
                return None
        return None
