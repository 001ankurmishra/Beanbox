import logging
import math
import secrets
from datetime import datetime, timezone
from typing import Optional

from app.cache.catalog_cache import InMemoryCatalogCache
from app.cache.interfaces import CatalogCache
from app.config import Settings
from app.models.domain import (
    CamelModel,
    Coupon,
    CouponType,
    Order,
    OrderAddressSnapshot,
    OrderItem,
    OrderPricing,
    OrderStatus,
    PaymentStatus,
)
from app.repositories.interfaces import (
    AddressRepository,
    CartRepository,
    CouponRepository,
    CreateOrderInput,
    OrderRepository,
    OrderUpdateFields,
    PaymentEventRepository,
    ProductRepository,
    Repositories,
    StockReservationItem,
    UserRepository,
)
from app.schemas.common import PaginationMeta
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
from app.services.payment_service import CreateCheckoutSessionInput, PaymentProvider
from app.services.pricing_service import (
    calculate_order_pricing,
    validate_coupon_for_subtotal,
)
from app.utils.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.worker.tasks_email import enqueue_email

logger = logging.getLogger("beanbox.orders")

CANCELLABLE_BY_CUSTOMER: frozenset[OrderStatus] = frozenset(
    {"pending", "paid", "processing"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_order_number() -> str:
    now = datetime.now(timezone.utc)
    suffix = 1000 + secrets.randbelow(9000)
    return f"BB-{now:%Y%m%d}-{suffix}"


class CouponSummary(CamelModel):
    code: str
    description: str
    type: CouponType
    value: int


class CheckoutPreviewResult(CamelModel):
    items: list[OrderItem]
    pricing: OrderPricing
    coupon: Optional[CouponSummary] = None
    shipping_address_id: Optional[str] = None


class InvoiceSellerInfo(CamelModel):
    legal_name: str
    brand_name: str
    gstin: str
    address: str
    hsn_sac_code: str


class InvoiceItem(OrderItem):
    hsn_code: str
    taxable_value_paise: int
    gst_rate_percent: int


class OrderInvoice(CamelModel):
    invoice_number: str
    issued_at: str
    order_number: str
    order_status: OrderStatus
    payment_status: PaymentStatus
    seller: InvoiceSellerInfo
    buyer: OrderAddressSnapshot
    items: list[InvoiceItem]
    pricing: OrderPricing
    coupon_code: Optional[str] = None


class OrderService:
    def __init__(
        self,
        order_repo: OrderRepository,
        cart_repo: CartRepository,
        product_repo: ProductRepository,
        coupon_repo: CouponRepository,
        address_repo: AddressRepository,
        user_repo: UserRepository,
        payment_event_repo: PaymentEventRepository,
        payment_provider: PaymentProvider,
        email_service: EmailService,
        settings: Settings,
        catalog_cache: Optional[CatalogCache] = None,
        audit_service: Optional[AuditService] = None,
        repos: Optional[Repositories] = None,
    ) -> None:
        self._order_repo = order_repo
        self._cart_repo = cart_repo
        self._product_repo = product_repo
        self._coupon_repo = coupon_repo
        self._address_repo = address_repo
        self._user_repo = user_repo
        self._payment_event_repo = payment_event_repo
        self._payment_provider = payment_provider
        self._email_service = email_service
        self._settings = settings
        self._catalog_cache: CatalogCache = catalog_cache or InMemoryCatalogCache(
            enabled=False
        )
        self._audit_service = audit_service
        self._repos = repos

    def _resolve_cart_order_items(
        self, user_id: str
    ) -> tuple[list[OrderItem], int]:
        # IMPORTANT: Checkout and order creation ALWAYS read live product prices,
        # active status, and inventory directly from Postgres / ProductRepository,
        # NEVER from the catalog cache, so price changes and stock limits are exact.
        cart = self._cart_repo.find_by_user_id(user_id)
        if not cart or not cart.items:
            raise BadRequestError("Your cart is empty", code="EMPTY_CART")

        order_items: list[OrderItem] = []
        subtotal_paise = 0

        for cart_item in cart.items:
            resolved = self._product_repo.find_variant_by_id(
                cart_item.product_id, cart_item.variant_id
            )
            if not resolved or not resolved[0].is_active:
                raise ConflictError(
                    "One or more items in your cart are no longer available",
                    details={
                        "productId": cart_item.product_id,
                        "variantId": cart_item.variant_id,
                    },
                    code="ITEM_UNAVAILABLE",
                )
            product, variant = resolved
            line_total = variant.price_paise * cart_item.quantity
            subtotal_paise += line_total

            order_items.append(
                OrderItem(
                    product_id=product.id,
                    variant_id=variant.id,
                    sku=variant.sku,
                    product_name=product.name,
                    product_slug=product.slug,
                    variant_label=variant.label,
                    image=product.images[0]
                    if product.images
                    else "/images/products/beans-medium.svg",
                    unit_price_paise=variant.price_paise,
                    quantity=cart_item.quantity,
                    line_total_paise=line_total,
                )
            )

        return order_items, subtotal_paise

    def preview_checkout(
        self,
        user_id: str,
        coupon_code: Optional[str] = None,
        address_id: Optional[str] = None,
    ) -> CheckoutPreviewResult:
        order_items, subtotal_paise = self._resolve_cart_order_items(user_id)

        if address_id:
            addr = self._address_repo.find_by_id_for_user(address_id, user_id)
            if not addr or addr.user_id != user_id:
                raise NotFoundError("Selected shipping address not found")

        valid_coupon: Optional[Coupon] = None
        if coupon_code and coupon_code.strip():
            found = self._coupon_repo.find_by_code(coupon_code)
            valid_coupon = validate_coupon_for_subtotal(found, subtotal_paise)

        pricing = calculate_order_pricing(subtotal_paise, valid_coupon)
        return CheckoutPreviewResult(
            items=order_items,
            pricing=pricing,
            coupon=CouponSummary(
                code=valid_coupon.code,
                description=valid_coupon.description,
                type=valid_coupon.type,
                value=valid_coupon.value,
            )
            if valid_coupon
            else None,
            shipping_address_id=address_id,
        )

    def create_order(
        self, user_id: str, address_id: str, coupon_code: Optional[str] = None
    ) -> Order:
        address = self._address_repo.find_by_id_for_user(address_id, user_id)
        if not address or address.user_id != user_id:
            raise NotFoundError("Shipping address not found")

        order_items, subtotal_paise = self._resolve_cart_order_items(user_id)

        applied_coupon: Optional[Coupon] = None
        if coupon_code and coupon_code.strip():
            found = self._coupon_repo.find_by_code(coupon_code)
            validated = validate_coupon_for_subtotal(found, subtotal_paise)
            reserved = self._coupon_repo.increment_usage_if_available(
                validated.id, _now_iso()
            )
            if not reserved:
                raise ConflictError(
                    "Coupon usage limit was just reached or coupon expired",
                    code="COUPON_UNAVAILABLE",
                )
            applied_coupon = reserved

        reservation_items = [
            StockReservationItem(
                product_id=i.product_id,
                variant_id=i.variant_id,
                quantity=i.quantity,
            )
            for i in order_items
        ]
        stock_result = self._product_repo.reserve_stock(reservation_items)
        if not stock_result.ok:
            if applied_coupon:
                self._coupon_repo.decrement_usage(applied_coupon.id)
            raise ConflictError(
                "Insufficient stock for one or more items in your cart",
                details={"failures": stock_result.failures},
                code="INSUFFICIENT_STOCK",
            )

        pricing = calculate_order_pricing(
            subtotal_paise, applied_coupon, already_reserved=True
        )
        order = self._order_repo.create(
            CreateOrderInput(
                order_number=_generate_order_number(),
                user_id=user_id,
                items=order_items,
                shipping_address=OrderAddressSnapshot(
                    label=address.label,
                    full_name=address.full_name,
                    phone=address.phone,
                    line1=address.line1,
                    line2=address.line2,
                    city=address.city,
                    state=address.state,
                    postal_code=address.postal_code,
                    country="India",
                ),
                coupon_code=applied_coupon.code if applied_coupon else None,
                coupon_id=applied_coupon.id if applied_coupon else None,
                pricing=pricing,
            )
        )
        self._cart_repo.clear_for_user(user_id)
        self._catalog_cache.invalidate_catalog("order_created")
        return order

    def create_payment_session(self, user_id: str, order_id: str):
        order = self._order_repo.find_by_id_for_user(order_id, user_id)
        if not order or order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.status != "pending":
            raise ConflictError(
                f"Cannot initiate payment for order in '{order.status}' status"
            )

        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        base_frontend = self._settings.frontend_url.rstrip("/")
        session = self._payment_provider.create_checkout_session(
            CreateCheckoutSessionInput(
                order=order,
                customer_email=user.email,
                success_url=f"{base_frontend}/orders/success?orderId={order.id}&sessionId={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base_frontend}/account/orders/{order.id}",
            )
        )
        self._order_repo.attach_payment_session(
            order.id,
            provider=session.provider,
            session_id=session.session_id,
            payment_intent_id=session.payment_intent_id,
        )
        return session

    def release_order_resources(self, order: Order) -> None:
        if not order.stock_released:
            self._product_repo.release_stock(
                [
                    StockReservationItem(
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                    )
                    for item in order.items
                ]
            )
            self._catalog_cache.invalidate_catalog("admin_order_stock_released")
        if order.coupon_id:
            self._coupon_repo.decrement_usage(order.coupon_id)

    def handle_payment_webhook(
        self, raw_body: bytes, signature_header: str
    ) -> dict:
        event = self._payment_provider.verify_webhook_event(raw_body, signature_header)

        if self._payment_event_repo.has_processed_event(event.event_id):
            return {"received": True, "duplicate": True}

        if event.type == "ignored":
            claimed_evt = self._payment_event_repo.claim_event(
                event_id=event.event_id,
                provider=event.provider,
                event_type=event.type,
            )
            if not claimed_evt:
                return {"received": True, "duplicate": True}
            return {"received": True, "duplicate": False, "status": "ignored"}

        order = (
            self._order_repo.find_by_id(event.order_id) if event.order_id else None
        )
        if not order and event.session_id:
            order = self._order_repo.find_by_payment_session_id(event.session_id)

        if not order:
            claimed_evt = self._payment_event_repo.claim_event(
                event_id=event.event_id,
                provider=event.provider,
                event_type=event.type,
            )
            if not claimed_evt:
                return {"received": True, "duplicate": True}
            return {"received": True, "duplicate": False, "status": "order_not_found"}

        if event.type == "payment_succeeded":
            if (
                event.amount_paise is not None
                and event.amount_paise != order.pricing.total_paise
            ):
                raise BadRequestError(
                    "Payment amount mismatch detected during webhook verification",
                    details={
                        "expectedPaise": order.pricing.total_paise,
                        "receivedPaise": event.amount_paise,
                    },
                    code="AMOUNT_MISMATCH",
                )

            updates = (
                OrderUpdateFields(
                    status="paid",
                    payment_status="paid",
                    payment_intent_id=event.payment_intent_id
                    or order.payment_intent_id,
                    paid_at=_now_iso(),
                )
                if order.status == "pending"
                else None
            )
            claimed_evt, updated = self._order_repo.apply_webhook_transition(
                order_id=order.id,
                expected_status="pending" if updates else None,
                updates=updates,
                event_id=event.event_id,
                provider=event.provider,
                event_type=event.type,
                payment_event_repo=self._payment_event_repo,
            )
            if not claimed_evt:
                return {"received": True, "duplicate": True}
            if updated:
                user = self._user_repo.find_by_id(order.user_id)
                if user:
                    enqueue_email(
                        kind="order_confirmation",
                        payload_ids={"order_id": updated.id, "user_id": updated.user_id},
                        email_service=self._email_service,
                        repos=self._repos,
                    )
                return {"received": True, "duplicate": False, "status": "paid"}

            # Edge case: A successful payment webhook arrived AFTER the order expired or was cancelled!
            # The event was claimed idempotently (claimed_evt is True).
            # We trigger an automatic refund through the payment provider, email the customer,
            # update the order status and payment_status to 'refunded', and write an audit log entry.
            latest = self._order_repo.find_by_id(order.id)
            latest_status = latest.status if latest else order.status
            if latest_status in ("cancelled", "refunded"):
                refund_amount = (
                    event.amount_paise
                    if event.amount_paise is not None
                    else order.pricing.total_paise
                )
                payment_intent_id = (
                    event.payment_intent_id
                    or (latest.payment_intent_id if latest else order.payment_intent_id)
                    or ""
                )

                refunded_order = self.process_order_refund(
                    order=latest or order,
                    refund_amount=refund_amount,
                    payment_intent_id=payment_intent_id,
                    new_status="refunded",
                    reason="Payment received after order was expired or cancelled",
                )
                if not refunded_order:
                    return {
                        "received": True,
                        "duplicate": True,
                        "status": "refunded",
                        "refunded": False,
                    }

                if self._audit_service:
                    self._audit_service.record(
                        event_type="order.late_payment_refunded",
                        outcome="success",
                        user_id=order.user_id,
                        target_id=order.id,
                        metadata={
                            "order_id": order.id,
                            "order_number": order.order_number,
                            "amount_paise": refund_amount,
                            "event_id": event.event_id,
                            "payment_intent_id": payment_intent_id,
                            "reason": "payment_succeeded_post_cancellation",
                        },
                    )

                return {
                    "received": True,
                    "duplicate": False,
                    "status": "refunded",
                    "refunded": True,
                }

            return {
                "received": True,
                "duplicate": False,
                "status": latest_status,
            }

        # payment_failed or session_expired -> conditionally claim pending->cancelled + release stock once
        fail_updates = (
            OrderUpdateFields(
                status="cancelled",
                payment_status="expired"
                if event.type == "session_expired"
                else "failed",
                stock_released=True,
                cancelled_at=_now_iso(),
                cancel_reason="Payment session expired"
                if event.type == "session_expired"
                else "Payment failed",
            )
            if order.status == "pending"
            else None
        )
        claimed_evt, updated = self._order_repo.apply_webhook_transition(
            order_id=order.id,
            expected_status="pending" if fail_updates else None,
            updates=fail_updates,
            event_id=event.event_id,
            provider=event.provider,
            event_type=event.type,
            payment_event_repo=self._payment_event_repo,
        )
        if not claimed_evt:
            return {"received": True, "duplicate": True}
        if updated:
            self._release_stock_and_coupon(updated)
        return {"received": True, "duplicate": False, "status": "cancelled"}

    def _release_stock_and_coupon(self, order: Order) -> None:
        self._product_repo.release_stock(
            [
                StockReservationItem(
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    quantity=item.quantity,
                )
                for item in order.items
            ]
        )
        if order.coupon_id:
            self._coupon_repo.decrement_usage(order.coupon_id)
        self._catalog_cache.invalidate_catalog("stock_released")

    def list_user_orders(self, user_id: str, page: int, limit: int) -> dict:
        items, total = self._order_repo.list_by_user_id(user_id, page, limit)
        total_pages = max(1, math.ceil(total / limit))
        return {
            "items": items,
            "pagination": PaginationMeta(
                page=page,
                limit=limit,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }

    def get_order_for_user(
        self,
        order_id: str,
        user_id: str,
        is_admin: bool = False,
        *,
        is_admin_role: bool = False,
    ) -> Order:
        if is_admin:
            order = self._order_repo.find_by_id(order_id)
            if not order:
                raise NotFoundError("Order not found")
            return order

        order = self._order_repo.find_by_id_for_user(order_id, user_id)
        if not order or order.user_id != user_id:
            if is_admin_role:
                raise ForbiddenError(
                    "Two-factor authentication is required for administrator access. Please enable 2FA in Security Settings.",
                    code="ADMIN_2FA_REQUIRED",
                )
            raise NotFoundError("Order not found")
        return order

    def process_order_refund(
        self,
        order: Order,
        refund_amount: Optional[int] = None,
        payment_intent_id: Optional[str] = None,
        new_status: Optional[OrderStatus] = "refunded",
        reason: Optional[str] = None,
    ) -> Optional[Order]:
        """
        Atomically claims and processes an order refund:
        1. UPDATE orders SET payment_status='refunded' (and status where valid)
           WHERE id=%s AND payment_status <> 'refunded' RETURNING *;
        2. Calls payment provider with idempotency key (refund:{order_id}) ONLY if the claim succeeded.
        3. If the provider call fails, reverts the claim so the order is never left in a refunded status.
        4. Enqueues order_refunded notification email.
        """
        amount = (
            refund_amount
            if refund_amount is not None
            else order.pricing.total_paise
        )
        pi_id = payment_intent_id or order.payment_intent_id or ""

        # Step 1: Claim refund atomically BEFORE calling payment provider
        claimed = self._order_repo.claim_refund(
            order_id=order.id,
            status=new_status,
            payment_intent_id=pi_id or None,
        )
        if not claimed:
            logger.info("Order %s already refunded; skipping duplicate refund claim", order.id)
            return None

        # Step 2: Call payment provider with idempotency key
        idempotency_key = f"refund:{order.id}"
        try:
            self._payment_provider.refund_payment(
                pi_id,
                amount,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            logger.error(
                "Payment provider refund failed for order %s (intent %s); reverting refund claim: %s",
                order.id,
                pi_id,
                exc,
            )
            self._order_repo.revert_refund_claim(
                order_id=order.id,
                previous_status=order.status,
                previous_payment_status=order.payment_status,
            )
            raise

        # Step 3: Enqueue customer notification email
        user = self._user_repo.find_by_id(order.user_id)
        if user:
            enqueue_email(
                kind="order_refunded",
                payload_ids={
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "amount_paise": amount,
                    "reason": reason or "Refund processed",
                },
                email_service=self._email_service,
                repos=self._repos,
            )

        return claimed

    def cancel_order(
        self, order_id: str, user_id: str, reason: Optional[str] = None
    ) -> Order:
        order = self.get_order_for_user(order_id, user_id, False)
        if order.status not in CANCELLABLE_BY_CUSTOMER:
            raise ConflictError(
                f"Order cannot be cancelled once it is '{order.status}'",
                details={"status": order.status},
                code="ORDER_NOT_CANCELLABLE",
            )

        cancel_reason = (reason or "").strip() or "Cancelled by customer before shipping"
        claimed = self._order_repo.claim_cancellation(
            order_id=order.id,
            user_id=user_id,
            cancel_reason=cancel_reason,
            cancelled_at=_now_iso(),
        )
        if not claimed:
            raise ConflictError(
                "Order has already been cancelled or updated",
                code="ORDER_NOT_CANCELLABLE",
            )

        self._release_stock_and_coupon(claimed)
        if claimed.payment_status == "paid":
            refunded_order = self.process_order_refund(
                order=claimed,
                new_status="cancelled",
                reason="Customer cancelled order",
            )
            return refunded_order or claimed

        return claimed

    def expire_order(self, order_id: str) -> Optional[Order]:
        """
        Atomically expires an unpaid pending order whose TTL has passed.
        Reuses the exact atomic claim pattern as cancel_order:
        UPDATE orders SET status='cancelled', stock_released=true, cancel_reason='payment_timeout'
        WHERE id=%s AND status='pending' AND stock_released=false RETURNING *.

        Releases reserved variant stock and coupon, invalidates catalog cache,
        and enqueues customer notification ONLY if the conditional claim returned a row.
        Safe against simultaneous races with customer cancellation and payment webhook.
        """
        claimed = self._order_repo.claim_expiry(
            order_id=order_id,
            cancel_reason="payment_timeout",
            cancelled_at=_now_iso(),
        )
        if not claimed:
            return None

        self._release_stock_and_coupon(claimed)

        user = self._user_repo.find_by_id(claimed.user_id)
        if user:
            enqueue_email(
                kind="order_expired",
                payload_ids={"order_id": claimed.id, "user_id": claimed.user_id},
                email_service=self._email_service,
                repos=self._repos,
            )

        return claimed

    def get_invoice(
        self,
        order_id: str,
        user_id: str,
        is_admin: bool = False,
        *,
        is_admin_role: bool = False,
    ) -> OrderInvoice:
        order = self.get_order_for_user(
            order_id, user_id, is_admin, is_admin_role=is_admin_role
        )
        return OrderInvoice(
            invoice_number=f"INV-{order.order_number}",
            issued_at=order.paid_at or order.created_at,
            order_number=order.order_number,
            order_status=order.status,
            payment_status=order.payment_status,
            seller=InvoiceSellerInfo(
                legal_name="BeanBox Specialty Coffee Roasters Pvt. Ltd.",
                brand_name="BeanBox",
                gstin="29AABCB4821K1Z5",
                address="No. 88, 12th Main Road, HAL 2nd Stage, Indiranagar, Bengaluru 560008, Karnataka",
                hsn_sac_code="0901",
            ),
            buyer=order.shipping_address,
            items=[
                InvoiceItem(
                    **item.model_dump(),
                    hsn_code="0901",
                    taxable_value_paise=item.line_total_paise,
                    gst_rate_percent=5,
                )
                for item in order.items
            ],
            pricing=order.pricing,
            coupon_code=order.coupon_code,
        )
