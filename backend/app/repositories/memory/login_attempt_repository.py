from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import LoginAttemptKeyType, LoginAttemptRecord
from app.repositories.interfaces import LoginAttemptRepository


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryLoginAttemptRepository(LoginAttemptRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[str, LoginAttemptRecord] = {}

    def get_by_key(self, key: str) -> Optional[LoginAttemptRecord]:
        with self._lock:
            rec = self._records.get(key)
            return rec.model_copy(deep=True) if rec else None

    def record_failure(
        self,
        key: str,
        key_type: LoginAttemptKeyType,
        max_failures: int = 5,
        base_lock_minutes: int = 15,
        failure_window_minutes: int = 15,
    ) -> LoginAttemptRecord:
        now = datetime.now(timezone.utc)
        now_iso = _iso(now)

        with self._lock:
            existing = self._records.get(key)
            if existing is None:
                failed_count = 1
                lockout_level = 0
                first_failed_at = now_iso
                locked_until: Optional[str] = None
                if failed_count >= max_failures:
                    lockout_level = 1
                    locked_until = _iso(now + timedelta(minutes=base_lock_minutes))
                rec = LoginAttemptRecord(
                    id=str(uuid4()),
                    key=key,
                    key_type=key_type,
                    failed_count=failed_count,
                    lockout_level=lockout_level,
                    first_failed_at=first_failed_at,
                    last_failed_at=now_iso,
                    locked_until=locked_until,
                )
                self._records[key] = rec.model_copy(deep=True)
                return rec

            rec = existing.model_copy(deep=True)
            last_dt = datetime.fromisoformat(rec.last_failed_at.replace("Z", "+00:00"))
            window_expired = (now - last_dt) > timedelta(minutes=failure_window_minutes)
            if window_expired:
                rec.failed_count = 1
                rec.lockout_level = 0
                rec.first_failed_at = now_iso
                rec.locked_until = None
            else:
                rec.failed_count += 1
            rec.last_failed_at = now_iso

            currently_locked = False
            if rec.locked_until:
                lock_dt = datetime.fromisoformat(
                    rec.locked_until.replace("Z", "+00:00")
                )
                currently_locked = lock_dt > now

            if not currently_locked and rec.failed_count >= max_failures:
                rec.lockout_level = min(rec.lockout_level + 1, 7)
                lock_minutes = base_lock_minutes * (2 ** (rec.lockout_level - 1))
                rec.locked_until = _iso(now + timedelta(minutes=lock_minutes))

            self._records[key] = rec.model_copy(deep=True)
            return rec

    def reset(self, key: str) -> None:
        with self._lock:
            self._records.pop(key, None)

    def cleanup_stale_attempts(
        self, idle_days: int = 7, batch_size: int = 1000
    ) -> int:
        now_dt = datetime.now(timezone.utc)
        cutoff = now_dt - timedelta(days=idle_days)
        with self._lock:
            stale_keys = []
            for k, rec in self._records.items():
                last_dt = datetime.fromisoformat(rec.last_failed_at.replace("Z", "+00:00"))
                if last_dt < cutoff:
                    if rec.locked_until:
                        lock_dt = datetime.fromisoformat(
                            rec.locked_until.replace("Z", "+00:00")
                        )
                        if lock_dt > now_dt:
                            continue
                    stale_keys.append(k)
            for k in stale_keys:
                del self._records[k]
            return len(stale_keys)
