"""
Abstract interfaces for BeanBox's rate limiter, catalog cache, session validity cache,
and idempotency store. Services and middleware depend on these interfaces cleanly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal, NamedTuple, Optional

from app.models.domain import Product
from app.repositories.interfaces import ProductListQuery


class RateLimitCheckResult(NamedTuple):
    """Unpackable result: `allowed, remaining, reset_at = limiter.check(...)`."""

    allowed: bool
    remaining: int
    reset_at: int


class RateLimiter(ABC):
    @abstractmethod
    def check(
        self, key: str, limit: int, window_seconds: int
    ) -> RateLimitCheckResult: ...


class CatalogCache(ABC):
    @abstractmethod
    def get_or_set_list(
        self,
        query: ProductListQuery,
        loader: Callable[[], dict[str, Any]],
        request_id: str = "-",
    ) -> tuple[dict[str, Any], bool]:
        """Returns `(payload_dict, is_cache_hit)`."""
        ...

    @abstractmethod
    def get_or_set_detail(
        self,
        slug: str,
        loader: Callable[[], Product],
        request_id: str = "-",
    ) -> tuple[Product, bool]:
        """Returns `(Product, is_cache_hit)`."""
        ...

    @abstractmethod
    def invalidate_catalog(self, reason: str) -> None: ...


class SessionCache(ABC):
    @abstractmethod
    def is_active(self, session_id: str) -> Optional[bool]:
        """Returns True if cached active, or None on miss/disabled."""
        ...

    @abstractmethod
    def mark_active(self, session_id: str, ttl_seconds: int = 30) -> None: ...

    @abstractmethod
    def invalidate(self, session_ids: Iterable[str]) -> None: ...


IdempotencyStatus = Literal["acquired", "in_progress", "replay", "conflict", "bypass"]


@dataclass(frozen=True)
class IdempotencyBeginResult:
    status: IdempotencyStatus
    status_code: int = 200
    body: Optional[dict[str, Any]] = None


class IdempotencyStore(ABC):
    @abstractmethod
    def begin(
        self,
        user_id: str,
        route_tag: str,
        client_key: str,
        body_hash: str,
        request_id: str = "-",
    ) -> IdempotencyBeginResult: ...

    @abstractmethod
    def complete(
        self,
        user_id: str,
        route_tag: str,
        client_key: str,
        body_hash: str,
        status_code: int,
        body: dict[str, Any],
    ) -> None: ...

    @abstractmethod
    def abort(self, user_id: str, route_tag: str, client_key: str) -> None: ...
