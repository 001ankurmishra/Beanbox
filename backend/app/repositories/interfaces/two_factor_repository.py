from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.domain import RecoveryCode, TotpSecret


class TwoFactorRepository(ABC):
    @abstractmethod
    def get_totp_secret(self, user_id: str) -> Optional[TotpSecret]: ...

    @abstractmethod
    def upsert_pending_totp(
        self, user_id: str, encrypted_secret: str
    ) -> TotpSecret: ...

    @abstractmethod
    def enable_totp(self, user_id: str) -> Optional[TotpSecret]: ...

    @abstractmethod
    def consume_totp_timestep(self, user_id: str, timestep: int) -> bool: ...

    @abstractmethod
    def consume_challenge_jti(self, jti: str, expires_at: str) -> bool: ...

    @abstractmethod
    def disable_totp(self, user_id: str) -> None: ...

    @abstractmethod
    def replace_recovery_codes(
        self, user_id: str, code_hashes: list[str]
    ) -> list[RecoveryCode]: ...

    @abstractmethod
    def consume_recovery_code(self, user_id: str, code_hash: str) -> bool: ...

    @abstractmethod
    def count_unused_recovery_codes(self, user_id: str) -> int: ...

    @abstractmethod
    def cleanup_consumed_challenges(self, batch_size: int = 1000) -> int: ...
