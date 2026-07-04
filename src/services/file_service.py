import os
import time
from pathlib import Path
from typing import Optional

from fastapi import Request

MAX_FILE_SIZE = 500 * 1024
FILE_TTL_SECONDS = 60 * 60
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

BASE_URL = os.environ.get("BASE_URL")


class FileEntry:
    __slots__ = ("path", "filename", "expires_at", "pin_hash")

    def __init__(self, path: Path, filename: str, expires_at: float, pin_hash: Optional[str]):
        self.path = path
        self.filename = filename
        self.expires_at = expires_at
        self.pin_hash = pin_hash


FILES: dict[str, FileEntry] = {}


class FileService:
    def __init__(self) -> None:
        from src.services.modules.download import DownloadService
        from src.services.modules.qr import QRService
        from src.services.modules.upload import UploadService

        self.upload_dir = UPLOAD_DIR
        self.FILES = FILES
        self.upload_service = UploadService()
        self.qr_service = QRService(self.upload_service)
        self.download_service = DownloadService()

    def cleanup_expired(self) -> None:
        self.upload_service.cleanup_expired()

    def public_base_url(self, request: Request) -> str:
        return self.upload_service.public_base_url(request)

    def hash_pin(self, pin: str) -> str:
        return self.upload_service.hash_pin(pin)

    def pin_matches(self, entry: FileEntry, submitted: str) -> bool:
        return self.upload_service.pin_matches(entry, submitted)

    def create_file(self, filename: str, contents: bytes, pin: str, request: Request) -> dict:
        return self.upload_service.create_file(filename, contents, pin, request)

    def get_entry(self, file_id: str) -> Optional[FileEntry]:
        self.cleanup_expired()
        return FILES.get(file_id)

    def build_qr_stream(self, request: Request, file_id: str):
        return self.qr_service.build_qr_stream(request, file_id)

    def build_download_response(self, file_id: str):
        return self.download_service.build_download_response(file_id)

    def delete_file(self, file_id: str) -> None:
        self.download_service.delete_file(file_id)

    def active_file_count(self) -> int:
        self.cleanup_expired()
        return len(FILES)


file_service = FileService()
