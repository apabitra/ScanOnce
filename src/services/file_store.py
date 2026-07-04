import time
from pathlib import Path
from typing import Optional

MAX_FILE_SIZE = 500 * 1024
FILE_TTL_SECONDS = 60 * 60
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


class FileEntry:
    __slots__ = ("path", "filename", "expires_at", "pin_hash", "pin_attempts", "pin_locked_until")

    def __init__(self, path: Path, filename: str, expires_at: float, pin_hash: Optional[str]):
        self.path = path
        self.filename = filename
        self.expires_at = expires_at
        self.pin_hash = pin_hash
        self.pin_attempts = 0
        self.pin_locked_until = 0.0


FILES: dict[str, FileEntry] = {}


def cleanup_expired(files: dict[str, FileEntry] | None = None) -> None:
    active_files = files if files is not None else FILES
    now = time.time()
    expired = [file_id for file_id, entry in list(active_files.items()) if entry.expires_at < now]
    for file_id in expired:
        entry = active_files.pop(file_id)
        entry.path.unlink(missing_ok=True)


def get_entry(file_id: str, files: dict[str, FileEntry] | None = None) -> Optional[FileEntry]:
    cleanup_expired(files)
    active_files = files if files is not None else FILES
    return active_files.get(file_id)


def delete_file(file_id: str, files: dict[str, FileEntry] | None = None) -> None:
    active_files = files if files is not None else FILES
    entry = active_files.pop(file_id, None)
    if entry:
        entry.path.unlink(missing_ok=True)


def active_file_count(files: dict[str, FileEntry] | None = None) -> int:
    cleanup_expired(files)
    active_files = files if files is not None else FILES
    return len(active_files)
