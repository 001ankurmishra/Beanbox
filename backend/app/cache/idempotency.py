"""
Idempotency key store for `POST /api/orders` and `POST /api/payments/checkout-session`.

Key format: `beanbox:{env}:idem:{user_id}:{route_tag}:{client_key}` (TTL = 86400s).
States:
  1. New key -> `SET key {"state":"in_progress","bodyHash":...} NX EX 86400` succeeds -> proceed.
  2. Completed same key + same body hash -> return stored response + `Idempotent-Replay: true`.
  3. In-progress same key + same body hash -> 409 Conflict.
  4. Same key + different body hash -> 422 Unprocessable Entity.
  5. Redis down -> log warning (throttled) & bypass idempotency cleanly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import redis
from fastapi import Request
from fastapi.responses import JSONResponse

from app.cache.connection import shared_redis_warnings
from app.cache.interfaces import IdempotencyBeginResult, IdempotencyStore
from app.cache.keys import (
    IDEMPOTENCY_TTL_SECONDS,
    STATS_COUNTER_TTL_SECONDS,
    hash_normalized_query,
    idempotency_key,
    stat_counter_key,
)
from app.utils.errors import AppError, BadRequestError, ConflictError
from app.utils.response import make_success_response, serialize_camel

logger = logging.getLogger("beanbox.idempotency")


class NoopIdempotencyStore(IdempotencyStore):
    """Fallback used when Redis is disabled (skips idempotency cleanly)."""

    def begin(
        self,
        user_id: str,
        route_tag: str,
        client_key: str,
        body_hash: str,
        request_id: str = "-",
    ) -> IdempotencyBeginResult:
        return IdempotencyBeginResult(status="bypass")

    def complete(
        self,
        user_id: str,
        route_tag: str,
        client_key: str,
        body_hash: str,
        status_code: int,
        body: dict[str, Any],
    ) -> None:
        return None

    def abort(self, user_id: str, route_tag: str, client_key: str) -> None:
        return None


class RedisIdempotencyStore(IdempotencyStore):
    def __init__(self, client: redis.Redis, app_env: str) -> None:
        self._client = client
        self._app_env = app_env

    def _record_replay_stat(self) -> None:
        try:
            skey = stat_counter_key(self._app_env, "idempotent_replays")
            pipe = self._client.pipeline()
            pipe.incr(skey)
            pipe.expire(skey, STATS_COUNTER_TTL_SECONDS)
            pipe.execute()
        except redis.RedisError:
            pass

    def begin(
        self,
        user_id: str,
        route_tag: str,
        client_key: str,
        body_hash: str,
        request_id: str = "-",
    ) -> IdempotencyBeginResult:
        rkey = idempotency_key(self._app_env, user_id, route_tag, client_key)
        initial_payload = json.dumps(
            {"state": "in_progress", "bodyHash": body_hash},
            separators=(",", ":"),
        )
        try:
            acquired = self._client.set(
                rkey, initial_payload, nx=True, ex=IDEMPOTENCY_TTL_SECONDS
            )
            if acquired:
                return IdempotencyBeginResult(status="acquired")

            raw = self._client.get(rkey)
            if raw is None:
                # Edge case: key expired right between SET NX and GET; try acquiring once more
                if self._client.set(
                    rkey, initial_payload, nx=True, ex=IDEMPOTENCY_TTL_SECONDS
                ):
                    return IdempotencyBeginResult(status="acquired")
                return IdempotencyBeginResult(status="in_progress")

            record = json.loads(raw)
            if record.get("bodyHash") != body_hash:
                return IdempotencyBeginResult(status="conflict")
            if record.get("state") != "done":
                return IdempotencyBeginResult(status="in_progress")

            self._record_replay_stat()
            logger.info(
                "idempotent=REPLAY route=%s key=%s req=%s",
                route_tag,
                client_key,
                request_id,
            )
            return IdempotencyBeginResult(
                status="replay",
                status_code=int(record.get("statusCode", 200)),
                body=record.get("body"),
            )
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "idempotency",
                "Redis idempotency store error (%s); bypassing idempotency check.",
                exc.__class__.__name__,
            )
            return IdempotencyBeginResult(status="bypass")

    def complete(
        self,
        user_id: str,
        route_tag: str,
        client_key: str,
        body_hash: str,
        status_code: int,
        body: dict[str, Any],
    ) -> None:
        rkey = idempotency_key(self._app_env, user_id, route_tag, client_key)
        payload = json.dumps(
            {
                "state": "done",
                "bodyHash": body_hash,
                "statusCode": status_code,
                "body": serialize_camel(body),
            },
            separators=(",", ":"),
        )
        try:
            self._client.set(rkey, payload, ex=IDEMPOTENCY_TTL_SECONDS)
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "idempotency_complete",
                "Redis idempotency complete write failed (%s).",
                exc.__class__.__name__,
            )

    def abort(self, user_id: str, route_tag: str, client_key: str) -> None:
        rkey = idempotency_key(self._app_env, user_id, route_tag, client_key)
        try:
            self._client.delete(rkey)
        except redis.RedisError:
            pass


def execute_idempotent(
    request: Request,
    user_id: str,
    route_tag: str,
    body_payload: Any,
    action: Callable[[], dict[str, Any]],
    success_status: int = 200,
) -> JSONResponse:
    """
    Runs a mutating route handler with optional `Idempotency-Key` enforcement.
    When Redis is down, `IdempotencyStore.begin` returns `bypass` and the action
    proceeds normally without blocking checkout.
    """
    raw_key = request.headers.get("idempotency-key")
    if not raw_key or not raw_key.strip():
        return make_success_response(action(), status_code=success_status)

    client_key = raw_key.strip()
    if len(client_key) > 128 or any(ch.isspace() for ch in client_key):
        raise BadRequestError(
            "Invalid Idempotency-Key header",
            code="INVALID_IDEMPOTENCY_KEY",
        )

    body_hash = hash_normalized_query(serialize_camel(body_payload))
    req_id = getattr(request.state, "request_id", "-")
    store: IdempotencyStore = request.app.state.cache.idempotency_store

    decision = store.begin(
        user_id=user_id,
        route_tag=route_tag,
        client_key=client_key,
        body_hash=body_hash,
        request_id=req_id,
    )
    if decision.status == "bypass":
        return make_success_response(action(), status_code=success_status)
    if decision.status == "in_progress":
        raise ConflictError(
            "A request with this Idempotency-Key is currently in progress.",
            code="IDEMPOTENCY_IN_PROGRESS",
        )
    if decision.status == "conflict":
        raise AppError(
            422,
            "IDEMPOTENCY_KEY_REUSE_CONFLICT",
            "Idempotency-Key was already used with a different request payload",
        )
    if decision.status == "replay":
        return JSONResponse(
            status_code=decision.status_code,
            content=decision.body,
            headers={"Idempotent-Replay": "true"},
        )

    try:
        data = action()
    except Exception:
        store.abort(user_id=user_id, route_tag=route_tag, client_key=client_key)
        raise

    envelope = {"success": True, "data": serialize_camel(data)}
    store.complete(
        user_id=user_id,
        route_tag=route_tag,
        client_key=client_key,
        body_hash=body_hash,
        status_code=success_status,
        body=envelope,
    )
    return JSONResponse(status_code=success_status, content=envelope)
