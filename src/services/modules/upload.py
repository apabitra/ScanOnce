import hashlib
import hmac
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Request

from src.services.file_service import FileEntry, FILES, MAX_FILE_SIZE, UPLOAD_DIR


class UploadService:
    def __init__(self) -> None:
        self.upload_dir = UPLOAD_DIR

    def cleanup_expired(self) -> None:
        now = time.time()
        expired = [file_id for file_id, entry in FILES.items() if entry.expires_at < now]
        for file_id in expired:
            entry = FILES.pop(file_id)
            entry.path.unlink(missing_ok=True)

    def public_base_url(self, request: Request) -> str:
        base_url = os.environ.get("BASE_URL")
        if base_url:
            return base_url.rstrip("/")

        import socket

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
            expires_at=time.time() + 60 * 60,
            pin_hash=pin_hash,
        )
        portal_url = f"{self.public_base_url(request)}/portal/{file_id}"
        return {"filename": filename, "portal_url": portal_url, "pin": pin}
