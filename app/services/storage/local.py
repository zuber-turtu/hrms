import os
import uuid
from typing import Optional, Tuple
from .base import BaseStorageProvider


class LocalStorageProvider(BaseStorageProvider):
    """
    Local filesystem storage provider that saves files to static/uploads/ and serves
    them directly via FastAPI static files mounting.
    """

    def __init__(self, base_upload_dir: str = "static/uploads"):
        self.base_upload_dir = base_upload_dir
        os.makedirs(self.base_upload_dir, exist_ok=True)

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = "avatars",
    ) -> Tuple[str, Optional[str]]:
        target_dir = os.path.join(self.base_upload_dir, folder or "misc")
        os.makedirs(target_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg" if "jpeg" in content_type else ".png"

        unique_filename = f"{uuid.uuid4().hex[:12]}{ext}"
        file_path = os.path.join(target_dir, unique_filename)

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # URL relative to domain
        relative_url = f"/static/uploads/{folder or 'misc'}/{unique_filename}"
        return relative_url, unique_filename

    def _is_safe_path(self, file_path: str) -> bool:
        """Defense-in-depth against directory traversal attacks."""
        resolved = os.path.abspath(file_path)
        base = os.path.abspath(self.base_upload_dir)
        return resolved.startswith(base)

    def delete_file(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
    def _resolve_local_path(self, file_identifier: str) -> Optional[str]:
        if not file_identifier:
            return None
        if file_identifier.startswith("/static/uploads/"):
            clean_rel = file_identifier.replace("/static/uploads/", "").lstrip("/\\")
            file_path = os.path.join(self.base_upload_dir, clean_rel)
        elif "/" in file_identifier or "\\" in file_identifier:
            clean_rel = file_identifier.lstrip("/\\")
            file_path = os.path.join(self.base_upload_dir, clean_rel)
        else:
            base_name = os.path.basename(file_identifier)
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
