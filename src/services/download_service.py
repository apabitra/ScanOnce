from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.services.file_store import FileEntry, FILES, delete_file


class DownloadService:
    def __init__(self, files: dict[str, FileEntry] | None = None) -> None:
        self.files = files if files is not None else FILES

    def build_download_response(self, file_id: str) -> FileResponse:
        entry = self.files.get(file_id)
        if not entry:
            raise LookupError("File not found, already downloaded, or expired")
        return FileResponse(
            entry.path,
            filename=entry.filename,
            media_type="application/octet-stream",
            background=BackgroundTask(self.delete_file, file_id),
        )

    def delete_file(self, file_id: str) -> None:
        delete_file(file_id, self.files)
