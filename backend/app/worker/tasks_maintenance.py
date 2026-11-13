"""
Scheduled roastery maintenance tasks: auth data garbage collection and daily low-stock digests.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.worker.celery_app import (
    celery_app,
    get_worker_redis,
    get_worker_repos,
    get_worker_services,
)
from app.worker.failures import TrackedTask
from app.worker.locks import task_lock
from app.worker.tasks_email import enqueue_email

logger = logging.getLogger("beanbox.worker.maintenance")

LAST_SUCCESS_KEY_CLEANUP = "beanbox:jobs:last_success:cleanup_expired_auth_data"
LAST_SUCCESS_KEY_LOW_STOCK = "beanbox:jobs:last_success:low_stock_digest"


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="app.worker.tasks_maintenance.cleanup_expired_auth_data",
    queue="maintenance",
)
def cleanup_expired_auth_data(self, request_id: Optional[str] = None) -> dict[str, Any]:
    """
    Hourly maintenance: deletes expired or used email verification / password reset tokens,
    expired sessions older than 30 days, expired consumed challenges, and login attempts idle > 7 days.
    Deletes in bounded batches of 1000 to prevent database locking or bloat.
    Protected by Redis distributed lock.
    """
    redis_client = get_worker_redis()

    with task_lock(redis_client, "cleanup_expired_auth_data", timeout=300) as acquired:
        if not acquired:
            logger.info("cleanup_expired_auth_data skipped: distributed lock already held")
            return {"status": "skipped", "reason": "lock_held"}

        repos = get_worker_repos()

        # 1. Cleanup expired or used verification & reset tokens
        del_v_tokens, del_r_tokens = repos.users.cleanup_expired_tokens(batch_size=1000)

        # 2. Cleanup expired sessions older than 30 days
        del_sessions = repos.sessions.cleanup_expired_sessions(
            older_than_days=30, batch_size=1000
        )

        # 3. Cleanup expired consumed 2FA challenge JTIs
        del_challenges = repos.two_factor.cleanup_consumed_challenges(batch_size=1000)

        # 4. Cleanup login attempts idle more than 7 days
        del_login_attempts = repos.login_attempts.cleanup_stale_attempts(
            idle_days=7, batch_size=1000
        )

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if redis_client:
            try:
                redis_client.set(LAST_SUCCESS_KEY_CLEANUP, now_iso, ex=86400 * 7)
            except Exception as exc:
                logger.warning("Failed to record cleanup last success timestamp: %s", exc)

        logger.info(
            "cleanup_expired_auth_data finished: verify_tokens=%d reset_tokens=%d sessions=%d challenges=%d login_attempts=%d",
            del_v_tokens,
            del_r_tokens,
            del_sessions,
            del_challenges,
            del_login_attempts,
        )

        return {
            "status": "success",
            "deleted_email_verification_tokens": del_v_tokens,
            "deleted_password_reset_tokens": del_r_tokens,
            "deleted_sessions": del_sessions,
            "deleted_consumed_challenges": del_challenges,
            "deleted_login_attempts": del_login_attempts,
            "timestamp": now_iso,
        }


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="app.worker.tasks_maintenance.low_stock_digest",
    queue="maintenance",
)
def low_stock_digest(self, request_id: Optional[str] = None) -> dict[str, Any]:
    """
    Daily maintenance (09:00 IST): identifies active coffee product variants
    with inventory <= 5 and dispatches an aggregated alert email to all roastery administrators.
    Protected by Redis distributed lock.
    """
    redis_client = get_worker_redis()

    with task_lock(redis_client, "low_stock_digest", timeout=300) as acquired:
        if not acquired:
            logger.info("low_stock_digest skipped: distributed lock already held")
            return {"status": "skipped", "reason": "lock_held"}

        repos = get_worker_repos()
        services = get_worker_services()

        # Query variants with stock <= 5
        low_stock_entries = repos.products.list_low_stock(threshold=5)

        items_summary = [
            {
                "product_id": entry.product_id,
                "product_name": entry.product_name,
                "variant_id": entry.variant.id,
                "variant_label": entry.variant.label,
                "sku": entry.variant.sku,
                "stock": entry.variant.stock,
            }
            for entry in low_stock_entries
        ]

        admins = repos.users.list_admins()
        emails_sent = 0

        if items_summary:
            for admin in admins:
                enqueue_email(
                    kind="low_stock_digest",
                    payload_ids={
                        "admin_id": admin.id,
                        "admin_email": admin.email,
                        "admin_name": admin.name,
                        "items": items_summary,
                    },
                    request_id=request_id,
                    email_service=services.email_service,
                    repos=repos,
                    redis_client=redis_client,
                )
                emails_sent += 1

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if redis_client:
            try:
                redis_client.set(LAST_SUCCESS_KEY_LOW_STOCK, now_iso, ex=86400 * 7)
            except Exception as exc:
                logger.warning("Failed to record low_stock_digest last success timestamp: %s", exc)

        logger.info(
            "low_stock_digest completed: variants_flagged=%d admins_notified=%d",
            len(items_summary),
            emails_sent,
        )
        return {
            "status": "success",
            "low_stock_count": len(items_summary),
            "admins_notified": emails_sent,
            "timestamp": now_iso,
        }
