from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import RecoveryCode, TotpSecret
from app.repositories.interfaces import TwoFactorRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryTwoFactorRepository(TwoFactorRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._secrets: dict[str, TotpSecret] = {}
        self._recovery_codes: list[RecoveryCode] = []

    def get_totp_secret(self, user_id: str) -> Optional[TotpSecret]:
        with self._lock:
            sec = self._secrets.get(user_id)
            return sec.model_copy(deep=True) if sec else None

    def upsert_pending_totp(
        self, user_id: str, encrypted_secret: str
    ) -> TotpSecret:
        now = _now_iso()
        with self._lock:
            existing = self._secrets.get(user_id)
            rec = TotpSecret(
                id=existing.id if existing else str(uuid4()),
                user_id=user_id,
                encrypted_secret=encrypted_secret,
                is_enabled=False,
                last_used_timestep=None,
                verified_at=None,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._secrets[user_id] = rec.model_copy(deep=True)
            return rec

    def enable_totp(self, user_id: str) -> Optional[TotpSecret]:
        now = _now_iso()
        with self._lock:
            sec = self._secrets.get(user_id)
            if not sec:
                return None
            sec.is_enabled = True
            sec.verified_at = now
            sec.updated_at = now
            return sec.model_copy(deep=True)

    def update_last_used_timestep(self, user_id: str, timestep: int) -> None:
        with self._lock:
            sec = self._secrets.get(user_id)
            if sec:
                sec.last_used_timestep = timestep
                sec.updated_at = _now_iso()

    def disable_totp(self, user_id: str) -> None:
        with self._lock:
            self._secrets.pop(user_id, None)
            self._recovery_codes = [
                c for c in self._recovery_codes if c.user_id != user_id
            ]

    def replace_recovery_codes(
        self, user_id: str, code_hashes: list[str]
    ) -> list[RecoveryCode]:
        now = _now_iso()
        with self._lock:
            self._recovery_codes = [
                c for c in self._recovery_codes if c.user_id != user_id
            ]
            created: list[RecoveryCode] = []
            for h in code_hashes:
                rc = RecoveryCode(
                    id=str(uuid4()),
                    user_id=user_id,
                    code_hash=h,
                    used_at=None,
                    created_at=now,
                )
                self._recovery_codes.append(rc.model_copy(deep=True))
                created.append(rc)
            return created

    def consume_recovery_code(self, user_id: str, code_hash: str) -> bool:
        with self._lock:
            for c in self._recovery_codes:
                if (
                    c.user_id == user_id
                    and c.code_hash == code_hash
                    and c.used_at is None
                ):
                    c.used_at = _now_iso()
                    return True
            return False

    def count_unused_recovery_codes(self, user_id: str) -> int:
        with self._lock:
            return sum(
                1
                for c in self._recovery_codes
                if c.user_id == user_id and c.used_at is None
            )
