"""
Order lifecycle background tasks: unpaid order expiration and stock restoration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import get_settings
from app.worker.celery_app import (
    celery_app,
    get_worker_redis,
    get_worker_repos,
    get_worker_services,
)
from app.worker.failures import TrackedTask
from app.worker.locks import task_lock

logger = logging.getLogger("beanbox.worker.orders")

LAST_SUCCESS_KEY_EXPIRE = "beanbox:jobs:last_success:expire_unpaid_orders"


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="app.worker.tasks_orders.expire_unpaid_orders",
    queue="maintenance",
)
def expire_unpaid_orders(self, request_id: Optional[str] = None) -> dict[str, Any]:
    """
    Finds pending orders older than PENDING_ORDER_TTL_MINUTES in batches of 100,
    oldest first, and atomically claims expiry.
    Releases reserved inventory and coupons, and notifies customers.
    Protected by Redis distributed lock against overlapping runs or dual Beat schedulers.
    """
    settings = get_settings()
    redis_client = get_worker_redis()

    with task_lock(redis_client, "expire_unpaid_orders", timeout=55) as acquired:
        if not acquired:
            logger.info("expire_unpaid_orders skipped: distributed lock already held")
            return {"status": "skipped", "reason": "lock_held"}

        repos = get_worker_repos()
        services = get_worker_services()

        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=settings.pending_order_ttl_minutes
        )
        cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")

        # Query batch of up to 100 oldest pending orders using partial index
        pending_orders = repos.orders.find_pending_orders_older_than(
            cutoff_iso=cutoff_iso, limit=100
        )

        expired_count = 0
        for order in pending_orders:
            # Atomic conditional claim: whoever updates the row first wins
            result = services.order_service.expire_order(order.id)
            if result is not None:
                expired_count += 1
                logger.info(
                    "Expired unpaid order id=%s order_number=%s",
                    order.id,
                    order.order_number,
                )

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if redis_client:
            try:
                redis_client.set(LAST_SUCCESS_KEY_EXPIRE, now_iso, ex=86400 * 7)
            except Exception as exc:
                logger.warning("Failed to record last success timestamp in Redis: %s", exc)

        logger.info(
            "expire_unpaid_orders finished: scanned=%d expired=%d cutoff=%s",
            len(pending_orders),
            expired_count,
            cutoff_iso,
        )
        return {
            "status": "success",
            "scanned": len(pending_orders),
            "expired": expired_count,
            "timestamp": now_iso,
        }
