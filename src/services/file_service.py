from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse

from src.services.download_service import DownloadService
from src.services.file_store import FILES, FileEntry
from src.services.qr_service import build_qr_stream as _build_qr_stream
from src.services.upload_service import UploadService

MAX_FILE_SIZE = 500 * 1024
FILE_TTL_SECONDS = 60 * 60


class FileService:
    def __init__(self) -> None:
        self.FILES = FILES
        self.upload_service = UploadService(self.FILES)
        self.download_service = DownloadService(self.FILES)

    def cleanup_expired(self) -> None:
        self.upload_service.cleanup_expired()

    def public_base_url(self, request: Request) -> str:
        return self.upload_service.public_base_url(request)

    def hash_pin(self, pin: str) -> str:
        return self.upload_service.hash_pin(pin)

    def pin_matches(self, entry: FileEntry, submitted: str) -> bool:
        return self.upload_service.pin_matches(entry, submitted)

    def check_pin_access(self, entry: FileEntry) -> tuple[bool, str | None]:
        return self.upload_service.check_pin_access(entry)

    def record_failed_pin_attempt(self, entry: FileEntry) -> tuple[bool, str | None]:
        return self.upload_service.record_failed_pin_attempt(entry)

    def create_file(self, filename: str, contents: bytes, pin: str, request: Request) -> dict:
        return self.upload_service.create_file(filename, contents, pin, request)

    def get_entry(self, file_id: str) -> FileEntry | None:
        return self.upload_service.get_entry(file_id)

    def build_qr_stream(self, request: Request, file_id: str) -> StreamingResponse:
        return _build_qr_stream(request, file_id, self.upload_service)

    def build_download_response(self, file_id: str) -> FileResponse:
        return self.download_service.build_download_response(file_id)

    def delete_file(self, file_id: str) -> None:
        self.download_service.delete_file(file_id)

    def active_file_count(self) -> int:
        return self.upload_service.active_file_count()


file_service = FileService()
