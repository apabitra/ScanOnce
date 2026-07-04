import os
import time
from pathlib import Path


class PINRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], list[float]] = {}

    def _load_config(self) -> tuple[int, int]:
        dotenv_path = Path(__file__).resolve().parents[3] / ".env"
        values: dict[str, str] = {}
        if dotenv_path.exists():
            for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")

        max_attempts = int(values.get("PIN_RATE_LIMIT_MAX_ATTEMPTS", os.getenv("PIN_RATE_LIMIT_MAX_ATTEMPTS", "5")))
        window_seconds = int(values.get("PIN_RATE_LIMIT_WINDOW_SECONDS", os.getenv("PIN_RATE_LIMIT_WINDOW_SECONDS", "300")))
        return max_attempts, window_seconds

    def allow_attempt(self, file_id: str, client_ip: str) -> bool:
        max_attempts, window_seconds = self._load_config()
        now = time.time()
        key = (file_id, client_ip or "unknown")
        attempts = [attempt for attempt in self._attempts.get(key, []) if now - attempt < window_seconds]
        if len(attempts) >= max_attempts:
            self._attempts[key] = attempts
            return False
        return True

    def record_failure(self, file_id: str, client_ip: str) -> None:
        max_attempts, window_seconds = self._load_config()
        now = time.time()
        key = (file_id, client_ip or "unknown")
        attempts = [attempt for attempt in self._attempts.get(key, []) if now - attempt < window_seconds]
        attempts.append(now)
        self._attempts[key] = attempts

    def reset(self, file_id: str, client_ip: str) -> None:
        self._attempts.pop((file_id, client_ip or "unknown"), None)

    def clear(self) -> None:
        self._attempts.clear()


pin_rate_limiter = PINRateLimiter()
