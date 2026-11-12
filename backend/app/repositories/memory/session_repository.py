from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import Session
from app.repositories.interfaces import CreateSessionInput, SessionRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_expired(expires_at: str) -> bool:
    dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return dt <= datetime.now(timezone.utc)


class InMemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: list[Session] = []

    def create(self, data: CreateSessionInput) -> Session:
        now = _now_iso()
        session = Session(
            id=str(uuid4()),
            user_id=data.user_id,
            refresh_token_hash=data.refresh_token_hash,
            previous_refresh_hashes=[],
            family_id=data.family_id,
            user_agent=data.user_agent,
            ip=data.ip,
            created_at=now,
            last_used_at=now,
            expires_at=data.expires_at,
            revoked_at=None,
        )
        with self._lock:
            self._sessions.append(session.model_copy(deep=True))
        return session

    def find_by_id(self, session_id: str) -> Optional[Session]:
        with self._lock:
            for s in self._sessions:
                if s.id == session_id:
                    return s.model_copy(deep=True)
            return None

    def find_by_refresh_hash(self, token_hash: str) -> Optional[Session]:
        with self._lock:
            for s in self._sessions:
                if s.refresh_token_hash == token_hash:
                    return s.model_copy(deep=True)
            return None

    def find_by_grace_refresh_hash(self, token_hash: str) -> Optional[Session]:
        with self._lock:
            for s in self._sessions:
                if s.grace_refresh_hash == token_hash:
                    return s.model_copy(deep=True)
            return None

    def find_by_previous_refresh_hash(self, token_hash: str) -> Optional[Session]:
        with self._lock:
            for s in self._sessions:
                if token_hash in s.previous_refresh_hashes:
                    return s.model_copy(deep=True)
            return None

    def rotate_refresh_token(
        self,
        session_id: str,
        expected_hash: str,
        new_hash: str,
        new_expires_at: str,
        ip: str,
        user_agent: str,
        grace_expires_at: Optional[str] = None,
        max_history: int = 100,
    ) -> Optional[Session]:
        with self._lock:
            for idx, s in enumerate(self._sessions):
                if (
                    s.id == session_id
                    and s.refresh_token_hash == expected_hash
                    and s.revoked_at is None
                ):
                    updated = s.model_copy(deep=True)
                    history = [*updated.previous_refresh_hashes, expected_hash]
                    if len(history) > max_history:
                        history = history[-max_history:]
                    updated.previous_refresh_hashes = history
                    updated.refresh_token_hash = new_hash
                    updated.grace_refresh_hash = (
                        expected_hash if grace_expires_at is not None else None
                    )
                    updated.grace_expires_at = grace_expires_at
                    updated.expires_at = new_expires_at
                    updated.ip = ip
                    updated.user_agent = user_agent
                    updated.last_used_at = _now_iso()
                    self._sessions[idx] = updated.model_copy(deep=True)
                    return updated
            return None

    def check_device_history(self, user_id: str, user_agent: str) -> tuple[bool, bool]:
        normalized = (user_agent or "").strip()
        with self._lock:
            user_sessions = [s for s in self._sessions if s.user_id == user_id]
            if not user_sessions:
                return False, False
            seen = any((s.user_agent or "").strip() == normalized for s in user_sessions)
            return True, seen

    def touch_last_used(self, session_id: str, ip: str, user_agent: str) -> None:
        with self._lock:
            for s in self._sessions:
                if s.id == session_id and s.revoked_at is None:
                    s.last_used_at = _now_iso()
                    if ip:
                        s.ip = ip
                    if user_agent:
                        s.user_agent = user_agent
                    return

    def list_active_for_user(self, user_id: str) -> list[Session]:
        with self._lock:
            active = [
                s.model_copy(deep=True)
                for s in self._sessions
                if s.user_id == user_id
                and s.revoked_at is None
                and not _is_expired(s.expires_at)
            ]
            active.sort(key=lambda x: x.last_used_at, reverse=True)
            return active

    def revoke_by_id(self, session_id: str, user_id: str) -> bool:
        with self._lock:
            for s in self._sessions:
                if s.id == session_id and s.user_id == user_id:
                    if s.revoked_at is None:
                        s.revoked_at = _now_iso()
                    return True
            return False

    def revoke_family(self, family_id: str) -> int:
        now = _now_iso()
        count = 0
        with self._lock:
            for s in self._sessions:
                if s.family_id == family_id and s.revoked_at is None:
                    s.revoked_at = now
                    count += 1
        return count

    def revoke_all_for_user(
        self, user_id: str, except_session_id: Optional[str] = None
    ) -> int:
        now = _now_iso()
        count = 0
        with self._lock:
            for s in self._sessions:
                if (
                    s.user_id == user_id
                    and s.revoked_at is None
                    and (except_session_id is None or s.id != except_session_id)
                ):
                    s.revoked_at = now
                    count += 1
        return count
