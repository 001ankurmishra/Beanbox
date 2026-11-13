from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import celery
import fakeredis
import pytest

from app.models.domain import Order, OrderAddressSnapshot, OrderItem, OrderPricing
from app.repositories.interfaces import CreateOrderInput, CreateSessionInput
from app.services.payment_service import VerifiedPaymentEvent
from app.worker.failures import record_dead_letter
from app.worker.locks import DistributedLock, task_lock
from app.worker.tasks_email import enqueue_email, send_email_task
from app.worker.tasks_maintenance import cleanup_expired_auth_data, low_stock_digest
from app.worker.tasks_orders import expire_unpaid_orders
from tests.conftest import (
    create_test_app,
    login_client,
    set_worker_test_doubles,
    sync_csrf,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_dummy_order(
    app,
    user_id: str,
    minutes_ago: int = 35,
    status: str = "pending",
    payment_status: Optional[str] = None,
) -> Order:
    created_at = _iso(_now() - timedelta(minutes=minutes_ago))
    prod = app.state.repos.products._products[0]
    variant = prod.variants[0]
    order = app.state.repos.orders.create(
        CreateOrderInput(
            order_number=f"BB-TEST-{minutes_ago}-{status}",
            user_id=user_id,
            items=[
                OrderItem(
                    product_id=prod.id,
                    variant_id=variant.id,
                    sku=variant.sku,
                    product_name=prod.name,
                    product_slug=prod.slug,
                    variant_label=variant.label,
                    image="/test.jpg",
                    unit_price_paise=50000,
                    quantity=2,
                    line_total_paise=100000,
                )
            ],
            shipping_address=OrderAddressSnapshot(
                label="Home",
                full_name="Test Customer",
                phone="9999999999",
                line1="123 Coffee St",
                city="Bengaluru",
                state="Karnataka",
                postal_code="560001",
            ),
            pricing=OrderPricing(
                items_subtotal_paise=100000,
                discount_paise=0,
                taxable_amount_paise=100000,
                gst_rate=5.0,
                gst_paise=5000,
                cgst_paise=2500,
                sgst_paise=2500,
                shipping_paise=0,
                total_paise=105000,
            ),
        )
    )
    # Manually set created_at and status
    with app.state.repos.orders._lock:
        for o in app.state.repos.orders._orders:
            if o.id == order.id:
                o.created_at = created_at
                o.status = status  # type: ignore[assignment]
                if payment_status is not None:
                    o.payment_status = payment_status  # type: ignore[assignment]
                return o.model_copy(deep=True)
    return order


# ============================================================================
# 1. EXPIRE ORDERS LOGIC
# ============================================================================

def test_expire_only_old_pending_orders():
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")
    assert user is not None

    # Order 1: 35 minutes ago, pending -> should expire
    o_old_pending = _make_dummy_order(app, user.id, minutes_ago=35, status="pending")

    # Order 2: 10 minutes ago, pending -> should NOT expire
    o_new_pending = _make_dummy_order(app, user.id, minutes_ago=10, status="pending")

    # Order 3: 45 minutes ago, paid -> should NOT expire
    o_old_paid = _make_dummy_order(app, user.id, minutes_ago=45, status="paid")

    res = expire_unpaid_orders()
    assert res["status"] == "success"
    assert res["scanned"] == 1
    assert res["expired"] == 1

    # Verify statuses
    after_old_pending = app.state.repos.orders.find_by_id(o_old_pending.id)
    assert after_old_pending.status == "cancelled"
    assert after_old_pending.cancel_reason == "payment_timeout"
    assert after_old_pending.stock_released is True

    after_new_pending = app.state.repos.orders.find_by_id(o_new_pending.id)
    assert after_new_pending.status == "pending"

    after_old_paid = app.state.repos.orders.find_by_id(o_old_paid.id)
    assert after_old_paid.status == "paid"


def test_expire_order_is_idempotent():
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")
    o = _make_dummy_order(app, user.id, minutes_ago=40, status="pending")

    first_claim = app.state.services.order_service.expire_order(o.id)
    assert first_claim is not None
    assert first_claim.status == "cancelled"
    assert first_claim.cancel_reason == "payment_timeout"

    # Second call must be a no-op returning None
    second_claim = app.state.services.order_service.expire_order(o.id)
    assert second_claim is None


def test_expire_vs_webhook_vs_cancel_race_threaded():
    """
    Races expire_order, customer cancel_order, and payment webhook simultaneously
    across 3 threads on 10 orders. In every case, exactly ONE thread wins.
    """
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    orders = [_make_dummy_order(app, user.id, minutes_ago=35, status="pending") for _ in range(10)]

    for o in orders:
        barrier = Barrier(3)
        results = {}

        def thread_expire():
            barrier.wait()
            results["expire"] = app.state.services.order_service.expire_order(o.id)

        def thread_cancel():
            barrier.wait()
            try:
                results["cancel"] = app.state.services.order_service.cancel_order(
                    o.id, user.id, "Customer cancellation"
                )
            except Exception as e:
                results["cancel"] = e

        def thread_webhook():
            barrier.wait()
            event = VerifiedPaymentEvent(
                event_id=f"evt_{o.id}",
                type="payment_succeeded",
                provider="mock",
                order_id=o.id,
                session_id=None,
                amount_paise=o.pricing.total_paise,
                payment_intent_id=f"pi_{o.id}",
                currency="INR",
            )
            with patch.object(app.state.services.payment_provider, "verify_webhook_event", return_value=event):
                results["webhook"] = app.state.services.order_service.handle_payment_webhook(b"{}", "sig")

        with ThreadPoolExecutor(max_workers=3) as executor:
            f1 = executor.submit(thread_expire)
            f2 = executor.submit(thread_cancel)
            f3 = executor.submit(thread_webhook)
            f1.result()
            f2.result()
            f3.result()

        final_order = app.state.repos.orders.find_by_id(o.id)
        # Final state must be either cancelled or paid
        assert final_order.status in ("cancelled", "paid")
        # If paid, stock was NOT released. If cancelled, stock was released exactly once.
        if final_order.status == "paid":
            assert final_order.stock_released is False
            assert results["webhook"].get("status") == "paid"
            assert results["expire"] is None
        else:
            assert final_order.status == "cancelled"
            assert final_order.stock_released is True
            # Either expire or cancel claimed the row
            expire_won = results["expire"] is not None
            cancel_won = not isinstance(results.get("cancel"), Exception)
            assert (expire_won and not cancel_won) or (cancel_won and not expire_won)


def test_late_payment_refund_edge_case():
    """
    A successful payment webhook arrives AFTER the order was expired or cancelled.
    Asserts:
    1. Payment event is recorded idempotently.
    2. Automatic refund triggered via payment provider.
    3. Order payment_status updated to 'refunded'.
    4. Customer notification email enqueued.
    5. Audit log entry recorded with event_type='order.late_payment_refunded'.
    """
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    order = _make_dummy_order(app, user.id, minutes_ago=40, status="pending")
    # Expire order first
    expired = app.state.services.order_service.expire_order(order.id)
    assert expired is not None
    assert expired.status == "cancelled"

    # Mock refund provider method
    app.state.services.payment_provider.refund_payment = MagicMock(return_value={"id": "re_test"})

    # Payment webhook arrives late
    event = VerifiedPaymentEvent(
        event_id="evt_late_paid_001",
        type="payment_succeeded",
        provider="mock",
        order_id=order.id,
        session_id=None,
        amount_paise=order.pricing.total_paise,
        payment_intent_id="pi_late_001",
        currency="INR",
    )

    with patch.object(app.state.services.payment_provider, "verify_webhook_event", return_value=event):
        res = app.state.services.order_service.handle_payment_webhook(b"{}", "sig")
    assert res["received"] is True
    assert res["status"] == "refunded"
    assert res["refunded"] is True

    # 1. Provider refund called with intent and total paise and idempotency key
    app.state.services.payment_provider.refund_payment.assert_called_once_with(
        "pi_late_001", order.pricing.total_paise, idempotency_key=f"refund:{order.id}"
    )

    # 2. Order payment_status updated
    updated_order = app.state.repos.orders.find_by_id(order.id)
    assert updated_order.payment_status == "refunded"

    # 3. Customer notified via email
    sent = app.state.services.email_service.get_sent_emails()
    refund_emails = [e for e in sent if e.type == "order_refunded" and e.to == user.email]
    assert len(refund_emails) == 1
    assert "Refund Issued" in refund_emails[0].subject

    # 4. Audit log entry recorded
    logs, _ = app.state.repos.audit_logs.list(page=1, limit=10, event_type="order.late_payment_refunded")
    assert len(logs) == 1
    assert logs[0].target_id == order.id
    assert logs[0].metadata["order_id"] == order.id

    # 5. Duplicate webhook delivery (same event ID) -> must NOT trigger refund again
    with patch.object(app.state.services.payment_provider, "verify_webhook_event", return_value=event):
        dup_res = app.state.services.order_service.handle_payment_webhook(b"{}", "sig")
    assert dup_res.get("duplicate") is True
    assert app.state.services.payment_provider.refund_payment.call_count == 1

    # 6. Alternate webhook event for already refunded order -> must NOT trigger refund again
    event_alt = VerifiedPaymentEvent(
        event_id="evt_late_paid_alt_999",
        type="payment_succeeded",
        provider="mock",
        order_id=order.id,
        session_id=None,
        amount_paise=order.pricing.total_paise,
        payment_intent_id="pi_late_001",
        currency="INR",
    )
    with patch.object(app.state.services.payment_provider, "verify_webhook_event", return_value=event_alt):
        dup_res_alt = app.state.services.order_service.handle_payment_webhook(b"{}", "sig")
    assert dup_res_alt.get("duplicate") is True
    assert dup_res_alt.get("refunded") is False
    assert app.state.services.payment_provider.refund_payment.call_count == 1


def test_order_cancelled_to_refunded_transition():
    """
    Verifies that 'cancelled' -> 'refunded' transition:
    1. Rejects with clear error (400 ORDER_NOT_PAID) if the order was never paid.
    2. Performs the real refund through the atomic path with idempotency key if paid.
    """
    app = create_test_app()
    app.state.services.payment_provider.refund_payment = MagicMock(return_value={"id": "re_admin"})
    admin_client = login_client(app, "admin@beanbox.in", "Admin@1234")
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    # Case 1: Cancelled order that was NEVER paid -> MUST reject transition
    order_unpaid = _make_dummy_order(app, user.id, minutes_ago=40, status="cancelled", payment_status="unpaid")
    res_unpaid = admin_client.patch(
        f"/api/admin/orders/{order_unpaid.id}/status",
        json={"status": "refunded", "reason": "Attempt refund on unpaid order"},
    )
    assert res_unpaid.status_code == 400, res_unpaid.text
    assert res_unpaid.json()["error"]["code"] == "ORDER_NOT_PAID"
    assert app.state.services.payment_provider.refund_payment.call_count == 0

    # Case 2: Cancelled order that WAS paid -> MUST execute real refund through atomic path
    order_paid = _make_dummy_order(app, user.id, minutes_ago=40, status="cancelled", payment_status="paid")
    res_paid = admin_client.patch(
        f"/api/admin/orders/{order_paid.id}/status",
        json={"status": "refunded", "reason": "Administrative refund after cancellation"},
    )
    assert res_paid.status_code == 200, res_paid.text
    updated = res_paid.json()["data"]["order"]
    assert updated["status"] == "refunded"
    assert updated["paymentStatus"] == "refunded"
    app.state.services.payment_provider.refund_payment.assert_called_once_with(
        order_paid.payment_intent_id or "",
        order_paid.pricing.total_paise,
        idempotency_key=f"refund:{order_paid.id}",
    )


def test_two_threads_duplicate_webhooks_race_single_refund():
    """
    Two threads delivering duplicate late-payment webhooks with DIFFERENT event IDs
    simultaneously must produce EXACTLY ONE refund call to the payment provider.
    """
    app = create_test_app()
    app.state.services.payment_provider.refund_payment = MagicMock(return_value={"id": "re_race"})
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")
    order = _make_dummy_order(app, user.id, minutes_ago=40, status="cancelled", payment_status="unpaid")

    event_1 = VerifiedPaymentEvent(
        event_id="evt_race_diff_1",
        type="payment_succeeded",
        provider="mock",
        order_id=order.id,
        session_id=None,
        amount_paise=order.pricing.total_paise,
        payment_intent_id="pi_race_001",
        currency="INR",
    )
    event_2 = VerifiedPaymentEvent(
        event_id="evt_race_diff_2",
        type="payment_succeeded",
        provider="mock",
        order_id=order.id,
        session_id=None,
        amount_paise=order.pricing.total_paise,
        payment_intent_id="pi_race_001",
        currency="INR",
    )

    barrier = Barrier(2)
    results: list[dict[str, Any]] = []

    def _deliver_webhook(evt: VerifiedPaymentEvent) -> None:
        barrier.wait()
        with patch.object(app.state.services.payment_provider, "verify_webhook_event", return_value=evt):
            out = app.state.services.order_service.handle_payment_webhook(b"{}", "sig")
            results.append(out)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_deliver_webhook, event_1)
        f2 = executor.submit(_deliver_webhook, event_2)
        f1.result()
        f2.result()

    assert len(results) == 2
    # Exactly one thread claimed and executed the refund
    refunded_results = [r for r in results if r.get("refunded") is True]
    duplicate_results = [r for r in results if r.get("duplicate") is True and r.get("refunded") is False]
    assert len(refunded_results) == 1
    assert len(duplicate_results) == 1

    # Exactly one refund call was dispatched to the provider with the idempotency key
    app.state.services.payment_provider.refund_payment.assert_called_once_with(
        "pi_race_001", order.pricing.total_paise, idempotency_key=f"refund:{order.id}"
    )

    # Order in database has payment_status='refunded'
    final_order = app.state.repos.orders.find_by_id(order.id)
    assert final_order.payment_status == "refunded"
    assert final_order.status == "refunded"


def test_refund_reverts_if_provider_call_fails():
    """
    If the payment provider refund call fails with an exception, the atomic claim
    must be reverted in the same code path so the order is never left in a refunded status.
    """
    app = create_test_app()
    app.state.services.payment_provider.refund_payment = MagicMock(
        side_effect=ConnectionError("Gateway timeout during refund")
    )
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")
    order = _make_dummy_order(app, user.id, minutes_ago=40, status="cancelled", payment_status="unpaid")

    event = VerifiedPaymentEvent(
        event_id="evt_fail_revert_1",
        type="payment_succeeded",
        provider="mock",
        order_id=order.id,
        session_id=None,
        amount_paise=order.pricing.total_paise,
        payment_intent_id="pi_fail_001",
        currency="INR",
    )

    with patch.object(app.state.services.payment_provider, "verify_webhook_event", return_value=event):
        with pytest.raises(ConnectionError):
            app.state.services.order_service.handle_payment_webhook(b"{}", "sig")

    # Order claim MUST be reverted back to cancelled/unpaid (NOT left as refunded)
    reverted_order = app.state.repos.orders.find_by_id(order.id)
    assert reverted_order.status == "cancelled"
    assert reverted_order.payment_status == "unpaid"


def test_enqueue_email_only_json_safe_primitives():
    """
    Verifies that enqueue_email only serializes JSON-safe primitives into Celery message kwargs
    and never injects repository, service, or complex objects.
    """
    import json
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    captured_kwargs: list[dict[str, Any]] = []

    def mock_apply_async(*args, **kwargs):
        task_kwargs = kwargs.get("kwargs", {})
        captured_kwargs.append(task_kwargs)

    with patch("app.worker.tasks_email.send_email_task.apply_async", side_effect=mock_apply_async):
        enqueue_email(
            kind="welcome",
            payload_ids={"user_id": user.id},
            email_service=app.state.services.email_service,
            repos=app.state.repos,
        )

    assert len(captured_kwargs) == 1
    kw = captured_kwargs[0]

    # Must be valid JSON
    serialized = json.dumps(kw)
    deserialized = json.loads(serialized)
    assert deserialized["kind"] == "welcome"
    assert deserialized["payload_ids"] == {"user_id": user.id}

    # Verify no service or repo object exists anywhere in task kwargs
    allowed_types = (str, int, float, bool, type(None), list, dict)
    for k, v in kw.items():
        assert isinstance(v, allowed_types)
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                assert isinstance(sub_v, allowed_types)

    # Reject non-JSON-safe payload_ids with ValueError
    with pytest.raises(ValueError) as excinfo:
        enqueue_email(
            kind="welcome",
            payload_ids={"invalid_obj": object()},
            email_service=app.state.services.email_service,
            repos=app.state.repos,
        )
    assert "Non-JSON-safe payload_ids" in str(excinfo.value)


# ============================================================================
# 2. EMAIL TASKS & DEDUPE
# ============================================================================

def test_email_dedupe_prevents_duplicate_sends():
    app = create_test_app()
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    set_worker_test_doubles(app.state.repos, app.state.services, fake_redis)

    user = app.state.repos.users.find_by_email("arjun@beanbox.in")
    order = _make_dummy_order(app, user.id, minutes_ago=5, status="paid")

    # First send: claims key, sends email
    res1 = send_email_task.apply(kwargs={"kind": "order_confirmation", "payload_ids": {"order_id": order.id}}).result
    assert res1["status"] == "sent"

    # Key exists in Redis
    assert fake_redis.exists(f"email:order_confirmation:{order.id}") == 1

    # Second send: duplicate delivery detected, skips sending
    res2 = send_email_task.apply(kwargs={"kind": "order_confirmation", "payload_ids": {"order_id": order.id}}).result
    assert res2["status"] == "skipped"
    assert res2["reason"] == "duplicate"

    # Confirm exactly ONE email was sent to email_service
    sent = [e for e in app.state.services.email_service.get_sent_emails() if e.type == "order_confirmation"]
    assert len(sent) == 1


def test_email_retry_after_failure_sends_exactly_once():
    """
    If the email send raises an exception on the first attempt after claiming the dedupe key,
    the key must be released so Celery's retry mechanism can send the email.
    Subsequent duplicate runs after success must be deduplicated.
    """
    app = create_test_app()
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    set_worker_test_doubles(app.state.repos, app.state.services, fake_redis)

    user = app.state.repos.users.find_by_email("arjun@beanbox.in")
    order = _make_dummy_order(app, user.id, minutes_ago=5, status="paid")
    dedupe_key = f"email:order_confirmation:{order.id}"

    # Attempt 1: Simulate mailer network error
    with patch.object(
        app.state.services.email_service,
        "send_order_confirmation",
        side_effect=ConnectionError("SMTP gateway unreachable"),
    ):
        with pytest.raises((ConnectionError, celery.exceptions.Retry)):
            send_email_task.apply(
                kwargs={"kind": "order_confirmation", "payload_ids": {"order_id": order.id}}
            ).get(disable_sync_subtasks=False)

    # Verify dedupe key was released on failure so retry can proceed
    assert fake_redis.get(dedupe_key) is None
    assert len(app.state.services.email_service.get_sent_emails()) == 0

    # Attempt 2: Celery retry runs when network recovers -> must succeed
    res_retry = send_email_task.apply(
        kwargs={"kind": "order_confirmation", "payload_ids": {"order_id": order.id}}
    ).result
    assert res_retry["status"] == "sent"
    assert fake_redis.get(dedupe_key) == "sent"

    sent_records = [
        e for e in app.state.services.email_service.get_sent_emails() if e.type == "order_confirmation"
    ]
    assert len(sent_records) == 1

    # Attempt 3: Subsequent duplicate delivery drops without sending again
    res_dup = send_email_task.apply(
        kwargs={"kind": "order_confirmation", "payload_ids": {"order_id": order.id}}
    ).result
    assert res_dup["status"] == "skipped"
    assert res_dup["reason"] == "duplicate"
    assert len(app.state.services.email_service.get_sent_emails()) == 1


def test_broker_down_fallback_sends_inline():
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    with patch("app.worker.tasks_email.send_email_task.apply_async", side_effect=Exception("Redis broker down")):
        # Enqueue should catch broker exception and deliver inline
        enqueue_email(
            kind="welcome",
            payload_ids={"user_id": user.id},
            email_service=app.state.services.email_service,
            repos=app.state.repos,
        )

    sent = [e for e in app.state.services.email_service.get_sent_emails() if e.type == "welcome" and e.to == user.email]
    assert len(sent) >= 1


# ============================================================================
# 3. DEAD LETTERS & RETRIES
# ============================================================================

def test_task_retries_and_dead_letter_row():
    app = create_test_app()
    failed_job_repo = app.state.repos.failed_jobs

    test_exc = ValueError("Permanent third-party payment gateway crash")
    job = record_dead_letter(
        task_name="app.worker.tasks_orders.expire_unpaid_orders",
        args=("order-123",),
        kwargs={"request_id": "req-xyz", "password": "MustBeRedacted"},
        exc=test_exc,
        traceback_str="Traceback (most recent call last):\n  File 'test.py', line 1, in test\nValueError: crash" * 50,
        attempts=5,
        queue="maintenance",
        repo=failed_job_repo,
    )
    assert job is not None
    assert job.task_name == "app.worker.tasks_orders.expire_unpaid_orders"
    assert job.attempts == 5
    assert job.queue == "maintenance"
    assert "ValueError" in job.error_message
    # Traceback capped at 4KB (4096 bytes)
    assert len(job.traceback) <= 4096
    # Arguments sanitized: password redacted, IDs preserved
    assert job.args_json["kwargs"]["password"] == "[REDACTED]"
    assert job.args_json["kwargs"]["request_id"] == "req-xyz"
    assert job.resolved_at is None

    # Retrieve from repository
    saved = failed_job_repo.find_by_id(job.id)
    assert saved is not None
    assert saved.id == job.id


# ============================================================================
# 4. MAINTENANCE TASKS
# ============================================================================

def test_cleanup_expired_auth_data():
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    # Add expired token and unexpired token
    past = _iso(_now() - timedelta(hours=2))
    future = _iso(_now() + timedelta(hours=2))
    app.state.repos.users.save_email_verification_token(user.id, "hash_expired", past)
    app.state.repos.users.save_email_verification_token(user.id, "hash_valid", future)

    # Add old session (>30 days) and recent session
    app.state.repos.sessions.create(
        CreateSessionInput(
            user_id=user.id,
            refresh_token_hash="hash_old",
            family_id="fam_old",
            user_agent="test",
            ip="127.0.0.1",
            expires_at=_iso(_now() - timedelta(days=35)),
        )
    )
    app.state.repos.sessions.create(
        CreateSessionInput(
            user_id=user.id,
            refresh_token_hash="hash_recent",
            family_id="fam_recent",
            user_agent="test",
            ip="127.0.0.1",
            expires_at=_iso(_now() + timedelta(days=10)),
        )
    )

    # Add idle login attempt (>7 days)
    app.state.repos.login_attempts._records["idle_key"] = app.state.repos.login_attempts.get_by_key("any") or (
        app.state.repos.login_attempts.record_failure("idle_key", "ip")
    )
    app.state.repos.login_attempts._records["idle_key"].last_failed_at = _iso(_now() - timedelta(days=10))

    # Add expired consumed challenge
    app.state.repos.two_factor._consumed_challenges["exp_jti"] = _now() - timedelta(minutes=5)
    app.state.repos.two_factor._consumed_challenges["valid_jti"] = _now() + timedelta(minutes=5)

    res = cleanup_expired_auth_data()
    assert res["status"] == "success"
    assert res["deleted_email_verification_tokens"] >= 1
    assert res["deleted_sessions"] >= 1
    assert res["deleted_consumed_challenges"] >= 1
    assert res["deleted_login_attempts"] >= 1

    # Verify unexpired items preserved
    assert app.state.repos.users.find_email_verification_token_by_hash("hash_valid") is not None
    assert "valid_jti" in app.state.repos.two_factor._consumed_challenges


def test_cleanup_never_deletes_unexpired_or_unused_rows():
    """
    Parity and safety test: verifies that cleanup_expired_auth_data
    NEVER deletes unexpired tokens, unused tokens, active sessions,
    valid 2FA challenges, or active locked login attempts.
    """
    app = create_test_app()
    user = app.state.repos.users.find_by_email("arjun@beanbox.in")

    now_dt = _now()
    past = _iso(now_dt - timedelta(hours=2))
    future = _iso(now_dt + timedelta(hours=2))

    # 1. Verification tokens: 1 expired, 1 used, 1 valid unexpired
    app.state.repos.users.save_email_verification_token(user.id, "hash_expired_v", past)
    used_v = app.state.repos.users.save_email_verification_token(user.id, "hash_used_v", future)
    app.state.repos.users.mark_email_verification_token_used(used_v.id)
    app.state.repos.users.save_email_verification_token(user.id, "hash_valid_unexpired_v", future)

    # 2. Password reset tokens: 1 expired, 1 valid unexpired
    app.state.repos.users.save_password_reset_token(user.id, "hash_expired_r", past)
    app.state.repos.users.save_password_reset_token(user.id, "hash_valid_unexpired_r", future)

    # 3. Sessions: 1 expired (>35 days), 1 active unexpired (<15 days)
    app.state.repos.sessions.create(
        CreateSessionInput(
            user_id=user.id,
            refresh_token_hash="hash_expired_sess",
            family_id="fam_exp",
            user_agent="test",
            ip="127.0.0.1",
            expires_at=_iso(now_dt - timedelta(days=35)),
        )
    )
    active_sess = app.state.repos.sessions.create(
        CreateSessionInput(
            user_id=user.id,
            refresh_token_hash="hash_active_sess",
            family_id="fam_act",
            user_agent="test",
            ip="127.0.0.1",
            expires_at=_iso(now_dt + timedelta(days=15)),
        )
    )

    # 4. 2FA challenges: 1 expired, 1 future valid
    app.state.repos.two_factor._consumed_challenges["jti_exp"] = now_dt - timedelta(minutes=5)
    app.state.repos.two_factor._consumed_challenges["jti_valid_future"] = now_dt + timedelta(minutes=15)

    # 5. Login attempts: 1 idle stale (>10 days, unlocked), 1 recent, 1 locked in future
    app.state.repos.login_attempts.record_failure("stale_idle_key", "ip")
    app.state.repos.login_attempts._records["stale_idle_key"].last_failed_at = _iso(now_dt - timedelta(days=10))

    app.state.repos.login_attempts.record_failure("recent_key", "ip")

    app.state.repos.login_attempts.record_failure("locked_key", "ip")
    app.state.repos.login_attempts._records["locked_key"].last_failed_at = _iso(now_dt - timedelta(days=10))
    app.state.repos.login_attempts._records["locked_key"].locked_until = _iso(now_dt + timedelta(hours=1))

    # Execute cleanup
    res = cleanup_expired_auth_data()
    assert res["status"] == "success"

    # ASSERT UNEXPIRED / UNUSED / ACTIVE ROWS ARE PRESERVED:
    assert app.state.repos.users.find_email_verification_token_by_hash("hash_valid_unexpired_v") is not None
    assert app.state.repos.users.find_email_verification_token_by_hash("hash_expired_v") is None
    assert app.state.repos.users.find_email_verification_token_by_hash("hash_used_v") is None

    assert app.state.repos.users.find_password_reset_token_by_hash("hash_valid_unexpired_r") is not None
    assert app.state.repos.users.find_password_reset_token_by_hash("hash_expired_r") is None

    assert app.state.repos.sessions.find_by_id(active_sess.id) is not None

    assert "jti_valid_future" in app.state.repos.two_factor._consumed_challenges
    assert "jti_exp" not in app.state.repos.two_factor._consumed_challenges

    assert "recent_key" in app.state.repos.login_attempts._records
    assert "locked_key" in app.state.repos.login_attempts._records
    assert "stale_idle_key" not in app.state.repos.login_attempts._records


def test_low_stock_digest():
    app = create_test_app()
    # Ensure variant stock is <= 5
    prod = app.state.repos.products._products[0]
    var = prod.variants[0]
    app.state.repos.products.update_variant_inventory(prod.id, var.id, 3)

    res = low_stock_digest()
    assert res["status"] == "success"
    assert res["low_stock_count"] >= 1
    assert res["admins_notified"] >= 1

    # Assert email sent to admin
    sent = app.state.services.email_service.get_sent_emails()
    admin_emails = [e for e in sent if e.type == "low_stock_digest"]
    assert len(admin_emails) >= 1
    assert "Low on Stock" in admin_emails[0].subject


# ============================================================================
# 5. OVERLAP PROTECTION (REDIS LOCK)
# ============================================================================

def test_lock_prevents_overlap():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)

    with task_lock(fake_redis, "overlap_test", timeout=30) as acquired1:
        assert acquired1 is True
        # Second attempt while lock is held must fail
        with task_lock(fake_redis, "overlap_test", timeout=30) as acquired2:
            assert acquired2 is False

    # After first lock exits, acquiring again succeeds
    with task_lock(fake_redis, "overlap_test", timeout=30) as acquired3:
        assert acquired3 is True


def test_lock_release_verifies_token():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    lock = DistributedLock(fake_redis, "token_check", timeout=30)
    assert lock.acquire() is True

    # Tamper with the token in Redis to simulate another process taking an expired lock
    fake_redis.set("beanbox:locks:token_check", "different_foreign_token")

    # Release should return False and NOT delete the other process's token
    assert lock.release() is False
    assert fake_redis.get("beanbox:locks:token_check") == "different_foreign_token"


# ============================================================================
# 6. ADMIN JOBS ENDPOINTS
# ============================================================================

def test_admin_jobs_telemetry_and_retry_endpoint():
    app = create_test_app()
    admin_client = login_client(app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin_client)

    # 1. Record a dead letter
    failed_job = record_dead_letter(
        task_name="app.worker.tasks_orders.expire_unpaid_orders",
        args=(),
        kwargs={"request_id": "test-req-123"},
        exc=RuntimeError("Test error"),
        traceback_str="Traceback...",
        attempts=5,
        queue="maintenance",
        repo=app.state.repos.failed_jobs,
    )
    assert failed_job is not None

    # 2. GET /api/admin/jobs
    res = admin_client.get("/api/admin/jobs")
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "queues" in data
    assert any(q["name"] == "maintenance" for q in data["queues"])
    assert "scheduledJobs" in data
    assert len(data["scheduledJobs"]) == 3
    assert len(data["failedJobs"]) >= 1
    assert data["failedJobs"][0]["id"] == failed_job.id

    # 3. POST /api/admin/jobs/failed/{id}/retry
    with patch("app.worker.celery_app.celery_app.send_task") as mock_send_task:
        retry_res = admin_client.post(f"/api/admin/jobs/failed/{failed_job.id}/retry")
        assert retry_res.status_code == 200, retry_res.text
        mock_send_task.assert_called_once_with(
            failed_job.task_name,
            args=[],
            kwargs={"request_id": "test-req-123"},
            queue="maintenance",
        )

    # 4. Verify job marked as resolved
    resolved = app.state.repos.failed_jobs.find_by_id(failed_job.id)
    assert resolved is not None
    assert resolved.resolved_at is not None
