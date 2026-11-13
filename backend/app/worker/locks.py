"""
Redis distributed lock with token verification on release via atomic Lua script.

Prevents concurrent execution of scheduled tasks across multiple Beat instances
or overlapping scheduled runs.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Generator, Optional

import redis

logger = logging.getLogger("beanbox.worker.locks")

# Atomic release: only delete the lock if the key still contains our unique token.
# This prevents deleting a lock that has expired and been acquired by another worker.
RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class DistributedLock:
    """
    Distributed mutual-exclusion lock built on Redis SET NX EX with Lua release.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis],
        key: str,
        timeout: int = 60,
    ) -> None:
        self.redis = redis_client
        self.key = f"beanbox:locks:{key}"
        self.timeout = timeout
        self.token = uuid.uuid4().hex
        self._acquired = False

    def acquire(self) -> bool:
        if self.redis is None:
            # Fallback when Redis is unavailable (e.g. strictly in-memory testing)
            self._acquired = True
            return True
        try:
            acquired = bool(
                self.redis.set(self.key, self.token, nx=True, ex=self.timeout)
            )
            self._acquired = acquired
            if not acquired:
                logger.info(
                    "Lock %s already held by another worker; acquisition skipped",
                    self.key,
                )
            return acquired
        except Exception as exc:
            logger.warning(
                "Failed to acquire lock %s due to Redis error: %s", self.key, exc
            )
            return False

    def release(self) -> bool:
        if not self._acquired or self.redis is None:
            return False
        try:
            res = self.redis.eval(RELEASE_LOCK_LUA, 1, self.key, self.token)
            return bool(res)
        except Exception as exc:
            logger.warning(
                "Failed to release lock %s due to Redis error: %s", self.key, exc
            )
            return False
        finally:
            self._acquired = False


@contextmanager
def task_lock(
    redis_client: Optional[redis.Redis],
    key: str,
    timeout: int = 60,
) -> Generator[bool, None, None]:
    """
    Context manager for acquiring and safely releasing a distributed lock.

    Example:
        with task_lock(redis_client, "expire_unpaid_orders", timeout=55) as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "lock_held"}
            # process task...
    """
    lock = DistributedLock(redis_client, key, timeout)
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
