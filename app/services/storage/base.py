from abc import ABC, abstractmethod
from typing import Optional, Tuple


class BaseStorageProvider(ABC):
    """
    Abstract Base Class defining the universal contract for all storage providers
    (Local Disk, Google Drive, AWS S3 / Cloudflare R2 / MinIO).
    """

    @abstractmethod
    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder: Optional[str] = "avatars",
    ) -> Tuple[str, Optional[str]]:
        """
        Uploads file to the designated storage backend.
        
        Returns:
            Tuple[str, Optional[str]]: (public_or_access_url, file_identifier_or_id)
        """
        pass

    @abstractmethod
    def delete_file(self, file_identifier: str) -> bool:
        """
        Deletes a file from storage given its identifier or file path.
        """
        pass

    def get_file_bytes(self, file_identifier: str) -> Optional[bytes]:
        """
        Fetches raw binary content of a file from storage.
        """
        return None

    def get_signed_download_url(
        self, file_identifier: str, expires_in_seconds: int = 900
    ) -> Optional[str]:
        """
        Generates a temporary pre-signed download URL for private documents.
        Defaults to None if direct stream is used.
        """
        return None

    def file_exists(self, file_identifier: str) -> bool:
        """
        Checks if a file exists and is accessible in the storage provider.
        """
        return False
