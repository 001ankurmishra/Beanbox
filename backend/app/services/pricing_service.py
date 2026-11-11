from datetime import datetime, timezone
from typing import Optional

from app.models.domain import Coupon, OrderPricing
from app.utils.errors import BadRequestError

FREE_SHIPPING_THRESHOLD_PAISE = 99900  # ₹999.00
STANDARD_SHIPPING_PAISE = 7900  # ₹79.00
GST_RATE = 0.05  # 5% Indian GST


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _round_half_up(value: float) -> int:
    # Deterministic commercial rounding matching JS Math.round
    return int(value + 0.5)


def validate_coupon_for_subtotal(
    coupon: Optional[Coupon],
    items_subtotal_paise: int,
    now: Optional[datetime] = None,
) -> Coupon:
    if coupon is None:
        raise BadRequestError("Invalid coupon code", code="INVALID_COUPON")
    if not coupon.is_active:
        raise BadRequestError("This coupon is no longer active", code="COUPON_INACTIVE")
    current_time = now or datetime.now(timezone.utc)
    if _parse_iso(coupon.expires_at) <= current_time:
        raise BadRequestError("This coupon has expired", code="COUPON_EXPIRED")
    if coupon.used_count >= coupon.usage_limit:
        raise BadRequestError(
            "This coupon has reached its usage limit",
            code="COUPON_LIMIT_REACHED",
        )
    if items_subtotal_paise < coupon.min_order_paise:
        min_inr = int(coupon.min_order_paise / 100)
        raise BadRequestError(
            f"Minimum order of ₹{min_inr} required to apply {coupon.code}",
            details={"minOrderPaise": coupon.min_order_paise},
            code="COUPON_MIN_ORDER_NOT_MET",
        )
    return coupon


def calculate_coupon_discount_paise(coupon: Coupon, items_subtotal_paise: int) -> int:
    if items_subtotal_paise <= 0:
        return 0

    if coupon.type == "percent":
        discount = _round_half_up((items_subtotal_paise * coupon.value) / 100.0)
        if coupon.max_discount_paise is not None:
            discount = min(discount, coupon.max_discount_paise)
    else:
        discount = coupon.value

    return max(0, min(discount, items_subtotal_paise))


def calculate_order_pricing(
    items_subtotal_paise: int,
    coupon: Optional[Coupon] = None,
    already_reserved: bool = False,
) -> OrderPricing:
    discount_paise = 0
    if coupon is not None:
        if not already_reserved:
            validate_coupon_for_subtotal(coupon, items_subtotal_paise)
        discount_paise = calculate_coupon_discount_paise(coupon, items_subtotal_paise)

    taxable_amount_paise = max(0, items_subtotal_paise - discount_paise)
    gst_paise = _round_half_up(taxable_amount_paise * GST_RATE)
    cgst_paise = gst_paise // 2
    sgst_paise = gst_paise - cgst_paise
    shipping_paise = (
        0
        if taxable_amount_paise == 0
        or taxable_amount_paise >= FREE_SHIPPING_THRESHOLD_PAISE
        else STANDARD_SHIPPING_PAISE
    )
    total_paise = taxable_amount_paise + gst_paise + shipping_paise

    return OrderPricing(
        items_subtotal_paise=items_subtotal_paise,
        discount_paise=discount_paise,
        taxable_amount_paise=taxable_amount_paise,
        gst_rate=GST_RATE,
        gst_paise=gst_paise,
        cgst_paise=cgst_paise,
        sgst_paise=sgst_paise,
        shipping_paise=shipping_paise,
        total_paise=total_paise,
        currency="INR",
    )
