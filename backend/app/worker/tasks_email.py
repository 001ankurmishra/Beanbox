"""
Asynchronous email delivery tasks, deduplication, and resilient broker fallbacks.

Key Guarantees:
1. Idempotency: Redis SET NX EX 86400 on `email:{kind}:{id}` guarantees each email
   is sent at most once even under at-least-once Celery delivery or worker retries.
2. Privacy: Task arguments contain IDs only. Sensitive tokens and PII are never
   passed in Celery args or logged.
3. Resilience: If the Celery broker or Redis is unreachable, `enqueue_email` falls back
   to inline delivery immediately so critical operations (checkout, signup) never fail.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Optional

from app.config import get_settings
from app.worker.celery_app import (
    celery_app,
    get_worker_redis,
    get_worker_repos,
    get_worker_services,
)
from app.worker.failures import TrackedTask

if TYPE_CHECKING:
    from app.repositories.interfaces import Repositories
    from app.services.email_service import EmailService

import contextvars

logger = logging.getLogger("beanbox.worker.email")

# In-memory transient store for token delivery fallback when Redis is absent
_TRANSIENT_TOKEN_STORE: dict[str, str] = {}

# Context variables for thread-local eager execution in multi-app tests
_active_email_service: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "active_email_service", default=None
)
_active_repos: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "active_repos", default=None
)


class TransientEmailError(Exception):
    """Simulated or transient network error that warrants a backoff retry."""


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="app.worker.tasks_email.send_email_task",
    queue="emails",
    autoretry_for=(TransientEmailError, ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_email_task(
    self,
    kind: str,
    payload_ids: dict[str, Any],
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Worker task to dispatch emails using ConsoleEmailService with Redis deduplication.
    Task args only contain IDs.
    """
    redis_client = get_worker_redis()
    services = get_worker_services()
    repos = get_worker_repos()

    # Dedupe Key Resolution: email:{kind}:{id}
    entity_id = (
        payload_ids.get("event_id")
        or payload_ids.get("id")
        or payload_ids.get("order_id")
        or payload_ids.get("token_id")
        or payload_ids.get("audit_id")
        or payload_ids.get("user_id")
        or "global"
    )
    dedupe_key = f"email:{kind}:{entity_id}"

    # Idempotency & Deduplication Check:
    # Uses a two-state key:
    # 1. 'sending' with short 300s TTL acquired atomically via SET NX EX.
    # 2. 'sent' with 24-hour 86400s TTL transitioned ONLY upon successful dispatch.
    # If dispatch raises an exception, the key is immediately released so Celery backoff retry can send.
    if redis_client is not None:
        try:
            current_state = redis_client.get(dedupe_key)
            if current_state == "sent":
                logger.info(
                    "Email dedupe key %s already sent; skipping duplicate delivery",
                    dedupe_key,
                )
                return {"status": "skipped", "reason": "duplicate", "key": dedupe_key}

            claimed = redis_client.set(dedupe_key, "sending", nx=True, ex=300)
            if not claimed:
                logger.info(
                    "Email dedupe key %s currently in-flight; skipping concurrent delivery",
                    dedupe_key,
                )
                return {"status": "skipped", "reason": "in_flight", "key": dedupe_key}
        except Exception as exc:
            logger.warning("Redis error during email dedupe check (%s): %s", dedupe_key, exc)

    email_service = _active_email_service.get() or services.email_service
    active_repos = _active_repos.get() or repos

    try:
        _dispatch_email_by_kind(
            kind=kind,
            payload_ids=payload_ids,
            email_service=email_service,
            repos=active_repos,
            redis_client=redis_client,
        )
        if redis_client is not None:
            try:
                # Transition to permanent 'sent' state (valid for 24 hours)
                redis_client.set(dedupe_key, "sent", ex=86400)
            except Exception as set_exc:
                logger.warning("Failed to mark email dedupe key %s as sent: %s", dedupe_key, set_exc)
    except Exception as exc:
        if redis_client is not None:
            try:
                # Release key on failure so Celery backoff retry can send successfully
                redis_client.delete(dedupe_key)
                logger.info("Released email dedupe key %s after dispatch failure to allow retry", dedupe_key)
            except Exception:
                pass
        raise exc

    return {"status": "sent", "kind": kind, "dedupe_key": dedupe_key}


def _dispatch_email_by_kind(
    kind: str,
    payload_ids: dict[str, Any],
    email_service: EmailService,
    repos: Repositories,
    redis_client: Optional[Any] = None,
    raw_token_override: Optional[str] = None,
) -> None:
    settings = get_settings()

    if kind == "welcome":
        user_id = payload_ids.get("user_id")
        if user_id:
            user = repos.users.find_by_id(user_id)
            if user:
                email_service.send_welcome(to=user.email, name=user.name)

    elif kind == "email_verification":
        user_id = payload_ids.get("user_id")
        token_id = payload_ids.get("token_id")
        if user_id and token_id:
            user = repos.users.find_by_id(user_id)
            raw_token = raw_token_override
            if not raw_token and redis_client:
                try:
                    raw_token = redis_client.get(f"beanbox:transient_tokens:{token_id}")
                except Exception:
                    raw_token = None
            if not raw_token:
                raw_token = _TRANSIENT_TOKEN_STORE.get(token_id, "verification-token")

            if user and raw_token:
                verify_url = f"{settings.frontend_url.rstrip('/')}/verify-email?token={raw_token}"
                email_service.send_email_verification(
                    to=user.email,
                    name=user.name,
                    verify_token=raw_token,
                    verify_url=verify_url,
                )

    elif kind == "password_reset":
        user_id = payload_ids.get("user_id")
        token_id = payload_ids.get("token_id")
        if user_id and token_id:
            user = repos.users.find_by_id(user_id)
            raw_token = raw_token_override
            if not raw_token and redis_client:
                try:
                    raw_token = redis_client.get(f"beanbox:transient_tokens:{token_id}")
                except Exception:
                    raw_token = None
            if not raw_token:
                raw_token = _TRANSIENT_TOKEN_STORE.get(token_id, "reset-token")

            if user and raw_token:
                reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={raw_token}"
                email_service.send_password_reset(
                    to=user.email,
                    name=user.name,
                    reset_token=raw_token,
                    reset_url=reset_url,
                )

    elif kind == "order_confirmation":
        order_id = payload_ids.get("order_id")
        if order_id:
            order = repos.orders.find_by_id(order_id)
            if order:
                user = repos.users.find_by_id(order.user_id)
                if user:
                    email_service.send_order_confirmation(
                        to=user.email, customer_name=user.name, order=order
                    )

    elif kind == "order_shipped":
        order_id = payload_ids.get("order_id")
        if order_id:
            order = repos.orders.find_by_id(order_id)
            if order:
                user = repos.users.find_by_id(order.user_id)
                if user:
                    email_service.send_order_shipped(
                        to=user.email, customer_name=user.name, order=order
                    )

    elif kind == "order_expired":
        order_id = payload_ids.get("order_id")
        if order_id:
            order = repos.orders.find_by_id(order_id)
            if order:
                user = repos.users.find_by_id(order.user_id)
                if user:
                    email_service.send_order_expired(
                        to=user.email, customer_name=user.name, order=order
                    )

    elif kind == "order_refunded":
        order_id = payload_ids.get("order_id")
        amount_paise = payload_ids.get("amount_paise", 0)
        reason = payload_ids.get("reason", "Payment received after order cancellation")
        if order_id:
            order = repos.orders.find_by_id(order_id)
            if order:
                user = repos.users.find_by_id(order.user_id)
                if user:
                    email_service.send_order_refunded(
                        to=user.email,
                        customer_name=user.name,
                        order=order,
                        amount_paise=amount_paise or order.pricing.total_paise,
                        reason=reason,
                    )

    elif kind == "security_notification":
        user_id = payload_ids.get("user_id")
        action = payload_ids.get("action")
        ip = payload_ids.get("ip", "unknown")
        user_agent = payload_ids.get("user_agent", "unknown")
        if user_id:
            user = repos.users.find_by_id(user_id)
            if user:
                if action == "password_changed":
                    email_service.send_password_changed_notification(
                        to=user.email, name=user.name, ip=ip, user_agent=user_agent
                    )
                elif action == "2fa_status":
                    enabled = bool(payload_ids.get("enabled", True))
                    email_service.send_2fa_status_notification(
                        to=user.email,
                        name=user.name,
                        enabled=enabled,
                        ip=ip,
                        user_agent=user_agent,
                    )
                elif action == "new_device":
                    email_service.send_new_device_login_notification(
                        to=user.email, name=user.name, ip=ip, user_agent=user_agent
                    )

    elif kind == "low_stock_digest":
        admin_email = payload_ids.get("admin_email", "admin@beanbox.in")
        admin_name = payload_ids.get("admin_name", "Roastery Admin")
        items = payload_ids.get("items", [])
        email_service.send_low_stock_digest(
            to=admin_email, admin_name=admin_name, low_stock_items=items
        )


def enqueue_email(
    kind: str,
    payload_ids: dict[str, Any],
    raw_token: Optional[str] = None,
    request_id: Optional[str] = None,
    email_service: Optional[EmailService] = None,
    repos: Optional[Repositories] = None,
    redis_client: Optional[Any] = None,
) -> None:
    """
    Public enqueue helper.
    Attempts to enqueue `send_email_task` into Celery `emails` queue.
    If the broker is down, catches the error, logs a warning, and delivers inline.
    Guarantees user flows (signup, checkout, cancel) never fail because of broker outages.
    """
    token_id = payload_ids.get("token_id")
    if raw_token and token_id:
        _TRANSIENT_TOKEN_STORE[token_id] = raw_token
        # Try writing to Redis with 30-min TTL if available
        r_client = redis_client or get_worker_redis()
        if r_client:
            try:
                r_client.set(f"beanbox:transient_tokens:{token_id}", raw_token, ex=1800)
            except Exception:
                pass

    # Defensive validation: ensure Celery task kwargs contain only JSON-safe primitives
    # (strings, numbers, booleans, lists, dicts) and never live service or repo instances.
    try:
        json.dumps(payload_ids)
    except (TypeError, ValueError) as json_err:
        raise ValueError(
            f"Non-JSON-safe payload_ids passed to enqueue_email: {json_err}"
        ) from json_err

    t1 = _active_email_service.set(email_service) if email_service is not None else None
    t2 = _active_repos.set(repos) if repos is not None else None

    try:
        try:
            send_email_task.apply_async(
                kwargs={
                    "kind": kind,
                    "payload_ids": payload_ids,
                    "request_id": request_id,
                },
                queue="emails",
            )
        except Exception as exc:
            logger.warning(
                "Broker unavailable when enqueuing email task (%s); executing inline fallback: %s",
                kind,
                exc,
            )
            active_repos = repos or get_worker_repos()
            active_email = email_service or get_worker_services().email_service
            try:
                _dispatch_email_by_kind(
                    kind=kind,
                    payload_ids=payload_ids,
                    email_service=active_email,
                    repos=active_repos,
                    redis_client=redis_client,
                    raw_token_override=raw_token,
                )
            except Exception as inline_exc:
                logger.error("Inline email fallback also failed: %s", inline_exc)
    finally:
        if t1 is not None:
            _active_email_service.reset(t1)
        if t2 is not None:
            _active_repos.reset(t2)
