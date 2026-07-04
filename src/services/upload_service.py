import hashlib
import hmac
import os
import secrets
import socket
import time
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Request

from src.services.file_store import (
    FILES,
    FILE_TTL_SECONDS,
    MAX_FILE_SIZE,
    UPLOAD_DIR,
    FileEntry,
    active_file_count,
    cleanup_expired,
    get_entry,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BASE_URL = os.environ.get("BASE_URL")
PIN_MAX_ATTEMPTS = int(os.environ.get("PIN_MAX_ATTEMPTS", "5"))
PIN_LOCKOUT_SECONDS = int(os.environ.get("PIN_LOCKOUT_SECONDS", "60"))


class UploadService:
    def __init__(self, files: dict[str, FileEntry] | None = None, upload_dir: Path | None = None) -> None:
        self.files = files if files is not None else FILES
        self.upload_dir = upload_dir or UPLOAD_DIR

    def cleanup_expired(self) -> None:
        cleanup_expired(self.files)

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

    def check_pin_access(self, entry: FileEntry) -> tuple[bool, str | None]:
        now = time.time()
        if entry.pin_locked_until and now < entry.pin_locked_until:
            return False, "PIN is temporarily locked due to too many failed attempts. Please try again later."

        if entry.pin_locked_until and now >= entry.pin_locked_until:
            entry.pin_locked_until = 0.0
            entry.pin_attempts = 0

        return True, None

    def record_failed_pin_attempt(self, entry: FileEntry) -> tuple[bool, str | None]:
        now = time.time()
        if entry.pin_locked_until and now < entry.pin_locked_until:
            return False, "PIN is temporarily locked due to too many failed attempts. Please try again later."

        entry.pin_attempts += 1
        if entry.pin_attempts >= PIN_MAX_ATTEMPTS:
            entry.pin_locked_until = now + PIN_LOCKOUT_SECONDS
            entry.pin_attempts = 0
            return False, "PIN is temporarily locked due to too many failed attempts. Please try again later."

        return True, None

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
        self.files[file_id] = FileEntry(
            path=dest,
            filename=filename,
            expires_at=time.time() + FILE_TTL_SECONDS,
            pin_hash=pin_hash,
        )
        portal_url = f"{self.public_base_url(request)}/portal/{file_id}"
        return {"filename": filename, "portal_url": portal_url, "pin": pin}

    def get_entry(self, file_id: str) -> Optional[FileEntry]:
        return get_entry(file_id, self.files)

    def active_file_count(self) -> int:
        return active_file_count(self.files)
