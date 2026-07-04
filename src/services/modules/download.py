from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.services.file_service import FILES


class DownloadService:
    def build_download_response(self, file_id: str) -> FileResponse:
        entry = FILES.get(file_id)
        if not entry:
            raise LookupError("File not found, already downloaded, or expired")
        return FileResponse(
            entry.path,
            filename=entry.filename,
            media_type="application/octet-stream",
            background=BackgroundTask(self.delete_file, file_id),
        )

    def delete_file(self, file_id: str) -> None:
        entry = FILES.pop(file_id, None)
        if entry:
            entry.path.unlink(missing_ok=True)
