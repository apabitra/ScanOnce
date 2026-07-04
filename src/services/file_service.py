import hashlib
import hmac
import io
import os
import secrets
import socket
import time
import uuid
from pathlib import Path
from typing import Optional

import qrcode
from fastapi import Request
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

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
        self.upload_dir = UPLOAD_DIR
        self.FILES = FILES

    def cleanup_expired(self) -> None:
        now = time.time()
        expired = [file_id for file_id, entry in FILES.items() if entry.expires_at < now]
        for file_id in expired:
            entry = FILES.pop(file_id)
            entry.path.unlink(missing_ok=True)

    def public_base_url(self, request: Request) -> str:
        if BASE_URL:
            return BASE_URL.rstrip("/")

        host = request.url.hostname or "localhost"
        if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.connect(("8.8.8.8", 80))
                    host = sock.getsockname()[0]
            except OSError:
                host = "127.0.0.1"

        port = request.url.port
        if port and port not in {80, 443}:
            return f"{request.url.scheme}://{host}:{port}"
        return f"{request.url.scheme}://{host}"

    def hash_pin(self, pin: str) -> str:
        return hashlib.sha256(pin.encode()).hexdigest()

    def pin_matches(self, entry: FileEntry, submitted: str) -> bool:
        return hmac.compare_digest(entry.pin_hash or "", self.hash_pin(submitted))

    def create_file(self, filename: str, contents: bytes, pin: str, request: Request) -> dict:
        self.cleanup_expired()
        if len(contents) > MAX_FILE_SIZE:
            raise ValueError(f"File too large ({len(contents)} bytes). Limit is {MAX_FILE_SIZE} bytes.")

        pin = pin.strip()
        if not pin:
            raise ValueError("PIN is required for every file upload")

        pin_hash = self.hash_pin(pin)
        file_id = secrets.token_urlsafe(24)
        dest = self.upload_dir / uuid.uuid4().hex
        dest.write_bytes(contents)
        FILES[file_id] = FileEntry(
            path=dest,
            filename=filename,
            expires_at=time.time() + FILE_TTL_SECONDS,
            pin_hash=pin_hash,
        )
        portal_url = f"{self.public_base_url(request)}/portal/{file_id}"
        return {"filename": filename, "portal_url": portal_url, "pin": pin}

    def get_entry(self, file_id: str) -> Optional[FileEntry]:
        self.cleanup_expired()
        return FILES.get(file_id)

    def build_qr_stream(self, request: Request, file_id: str):
        download_url = f"{self.public_base_url(request)}/redeem/{file_id}"
        img = qrcode.make(download_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")

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

    def active_file_count(self) -> int:
        self.cleanup_expired()
        return len(FILES)


file_service = FileService()
