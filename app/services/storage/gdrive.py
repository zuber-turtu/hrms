import io
import os
import uuid
from typing import Optional, Tuple
from .base import BaseStorageProvider


class GoogleDriveStorageProvider(BaseStorageProvider):
    """
    Google Drive Storage Provider using Service Account credentials.
    Uploads files to a shared Drive folder, sets public read permission,
    and returns Google's high-speed CDN image link (https://lh3.googleusercontent.com/d/{file_id}).
    """

    def __init__(
        self,
        service_account_file: Optional[str] = None,
        service_account_json: Optional[str] = None,
        folder_id: Optional[str] = None,
    ):
        self.service_account_file = service_account_file or os.getenv(
            "GDRIVE_SERVICE_ACCOUNT_FILE", "service_account.json"
        )
        self.service_account_json = service_account_json or os.getenv(
            "GDRIVE_SERVICE_ACCOUNT_JSON", None
        )
        self.folder_id = folder_id or os.getenv("GDRIVE_FOLDER_ID", "")
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service

        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import json

        creds = None
        if self.service_account_json and self.service_account_json.strip():
            raw = self.service_account_json.strip()
            try:
                info = json.loads(raw)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=self.scopes
                )
            except Exception:
                import base64
                decoded = base64.b64decode(raw).decode("utf-8")
                info = json.loads(decoded)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=self.scopes
                )
        elif self.service_account_file and os.path.exists(self.service_account_file):
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file, scopes=self.scopes
            )
        else:
            raise FileNotFoundError(
                f"Google Drive service account credentials not found. Provide '{self.service_account_file}' or set GDRIVE_SERVICE_ACCOUNT_JSON."
            )

        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = "avatars",
    ) -> Tuple[str, Optional[str]]:
        service = self._get_service()
        from googleapiclient.http import MediaIoBaseUpload

        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg" if "jpeg" in content_type else ".png"

        prefix = "doc" if folder == "documents" else "avatar"
        unique_filename = f"{prefix}_{uuid.uuid4().hex[:10]}{ext}"

        file_metadata = {"name": unique_filename}
        if self.folder_id:
            file_metadata["parents"] = [self.folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes), mimetype=content_type, resumable=True
        )

        created_file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )

        file_id = created_file.get("id")

        # Grant public read access so file can be embedded or viewed
        try:
            service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()
        except Exception:
            pass  # Permission might already be inherited from parent folder

        # Google's direct CDN or download URL
        if "pdf" in content_type or folder == "documents":
            cdn_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        else:
            cdn_url = f"https://lh3.googleusercontent.com/d/{file_id}"
        return cdn_url, file_id

    def delete_file(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        try:
            service = self._get_service()
            service.files().delete(fileId=file_identifier).execute()
            return True
        except Exception:
            return False

    def get_file_bytes(self, file_identifier: str) -> Optional[bytes]:
        if not file_identifier:
            return None
        try:
            service = self._get_service()
            from googleapiclient.http import MediaIoBaseDownload
            import io
            request = service.files().get_media(fileId=file_identifier)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return fh.getvalue()
        except Exception:
            return None

    def file_exists(self, file_identifier: str) -> bool:
        if not file_identifier:
            return False
        try:
            service = self._get_service()
            file_meta = service.files().get(fileId=file_identifier, fields="id,trashed").execute()
            return bool(file_meta and not file_meta.get("trashed", False))
        except Exception:
            return False
