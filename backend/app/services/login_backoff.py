import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from app.core.errors import AppError


@dataclass
class _Attempt:
    failures: int
    ready_at: float
    expires_at: float
    pending: bool = False


class LoginBackoff:
    """Bounded process-local protection, keyed by both username and transport IP."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        capacity: int = 4096,
        ttl: float = 900,
    ) -> None:
        self.clock = clock
        self.capacity = capacity
        self.ttl = ttl
        self._attempts: OrderedDict[str, _Attempt] = OrderedDict()

    def begin(self, username: str, ip: str) -> str:
        key = hashlib.sha256(f"{len(username)}:{username}{ip}".encode()).hexdigest()
        now = self.clock()
        expired = [key for key, value in self._attempts.items() if value.expires_at <= now]
        for old in expired:
            if not self._attempts[old].pending:
                del self._attempts[old]
        entry = self._attempts.get(key)
        if entry is not None and (entry.pending or entry.ready_at > now):
            raise AppError("auth.login_throttled", 429, "Invalid credentials.")
        if entry is None:
            if len(self._attempts) >= self.capacity:
                # Do not evict active restrictions: spraying new names must not reset backoff.
                raise AppError("auth.login_throttled", 429, "Invalid credentials.")
            entry = _Attempt(0, now, now + self.ttl)
            self._attempts[key] = entry
        entry.pending = True
        entry.expires_at = now + self.ttl
        return key

    def finish(self, key: str, *, success: bool, failed_credentials: bool = True) -> None:
        entry = self._attempts[key]
        if success or (not failed_credentials and entry.failures == 0):
            del self._attempts[key]
            return
        entry.pending = False
        if failed_credentials:
            entry.failures = min(entry.failures + 1, 7)
            entry.ready_at = self.clock() + min(2 ** (entry.failures - 1), 60)
            entry.expires_at = self.clock() + self.ttl
