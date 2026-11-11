import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import quote
from uuid import uuid4

import stripe

from app.config import Settings
from app.models.domain import CamelModel, Order
from app.utils.errors import BadRequestError


@dataclass
class CreateCheckoutSessionInput:
    order: Order
    customer_email: str
    success_url: str
    cancel_url: str


class CheckoutSessionResult(CamelModel):
    provider: Literal["stripe", "mock"]
    session_id: str
    payment_intent_id: Optional[str] = None
    checkout_url: str


@dataclass
class VerifiedPaymentEvent:
    event_id: str
    provider: Literal["stripe", "mock"]
    type: Literal["payment_succeeded", "payment_failed", "session_expired", "ignored"]
    order_id: Optional[str] = None
    session_id: Optional[str] = None
    payment_intent_id: Optional[str] = None
    amount_paise: Optional[int] = None
    currency: Optional[str] = None


class PaymentProvider(ABC):
    name: Literal["stripe", "mock"]

    @abstractmethod
    def create_checkout_session(
        self, data: CreateCheckoutSessionInput
    ) -> CheckoutSessionResult: ...

    @abstractmethod
    def verify_webhook_event(
        self, raw_body: bytes, signature_header: str
    ) -> VerifiedPaymentEvent: ...

    @abstractmethod
    def refund_payment(self, payment_intent_id: str, amount_paise: int) -> None: ...


def sign_mock_webhook_payload(raw_body: bytes | str, secret: str) -> str:
    payload = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"v1={digest}"


class MockPaymentProvider(PaymentProvider):
    name: Literal["stripe", "mock"] = "mock"

    def __init__(self, frontend_url: str, webhook_secret: str) -> None:
        self._frontend_url = frontend_url.rstrip("/")
        self._webhook_secret = webhook_secret

    def create_checkout_session(
        self, data: CreateCheckoutSessionInput
    ) -> CheckoutSessionResult:
        session_id = f"mock_sess_{uuid4().hex}"
        payment_intent_id = f"mock_pi_{uuid4().hex}"
        checkout_url = (
            f"{self._frontend_url}/checkout/mock-pay"
            f"?sessionId={quote(session_id)}&orderId={quote(data.order.id)}"
        )
        return CheckoutSessionResult(
            provider="mock",
            session_id=session_id,
            payment_intent_id=payment_intent_id,
            checkout_url=checkout_url,
        )

    def verify_webhook_event(
        self, raw_body: bytes, signature_header: str
    ) -> VerifiedPaymentEvent:
        if not signature_header:
            raise BadRequestError(
                "Missing webhook signature header", code="INVALID_SIGNATURE"
            )

        expected = sign_mock_webhook_payload(raw_body, self._webhook_secret)
        if not hmac.compare_digest(signature_header.strip(), expected):
            raise BadRequestError(
                "Invalid mock webhook signature", code="INVALID_SIGNATURE"
            )

        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise BadRequestError(
                "Malformed webhook JSON payload", code="INVALID_PAYLOAD"
            ) from exc

        event_id = parsed.get("id")
        event_type = parsed.get("type")
        event_data = parsed.get("data")
        if not event_id or not event_type or not isinstance(event_data, dict):
            raise BadRequestError(
                "Incomplete webhook event payload", code="INVALID_PAYLOAD"
            )

        mapped: Literal["payment_succeeded", "payment_failed", "session_expired", "ignored"] = (
            "ignored"
        )
        if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
            mapped = "payment_succeeded"
        elif event_type == "payment_intent.payment_failed":
            mapped = "payment_failed"
        elif event_type == "checkout.session.expired":
            mapped = "session_expired"

        return VerifiedPaymentEvent(
            event_id=event_id,
            provider="mock",
            type=mapped,
            order_id=event_data.get("orderId"),
            session_id=event_data.get("sessionId"),
            payment_intent_id=event_data.get("paymentIntentId"),
            amount_paise=event_data.get("amountPaise"),
            currency=event_data.get("currency"),
        )

    def refund_payment(self, payment_intent_id: str, amount_paise: int) -> None:
        return None


class StripePaymentProvider(PaymentProvider):
    name: Literal["stripe", "mock"] = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str) -> None:
        self._client = stripe.StripeClient(secret_key)
        self._webhook_secret = webhook_secret

    def create_checkout_session(
        self, data: CreateCheckoutSessionInput
    ) -> CheckoutSessionResult:
        order = data.order
        session = self._client.checkout.sessions.create(
            params={
                "mode": "payment",
                "customer_email": data.customer_email,
                "client_reference_id": order.id,
                "success_url": data.success_url,
                "cancel_url": data.cancel_url,
                "metadata": {
                    "orderId": order.id,
                    "orderNumber": order.order_number,
                },
                "line_items": [
                    {
                        "price_data": {
                            "currency": "inr",
                            "unit_amount": order.pricing.total_paise,
                            "product_data": {
                                "name": f"BeanBox Order {order.order_number}",
                                "description": f"{len(order.items)} item(s) including 5% GST & shipping",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            }
        )
        if not session.url:
            raise BadRequestError("Failed to obtain Stripe Checkout URL")

        pi = session.payment_intent if isinstance(session.payment_intent, str) else None
        return CheckoutSessionResult(
            provider="stripe",
            session_id=session.id,
            payment_intent_id=pi,
            checkout_url=session.url,
        )

    def verify_webhook_event(
        self, raw_body: bytes, signature_header: str
    ) -> VerifiedPaymentEvent:
        if not self._webhook_secret:
            raise BadRequestError("STRIPE_WEBHOOK_SECRET is not configured")

        try:
            event = stripe.Webhook.construct_event(
                payload=raw_body,
                sig_header=signature_header,
                secret=self._webhook_secret,
            )
        except Exception as exc:
            raise BadRequestError(
                "Invalid Stripe webhook signature", code="INVALID_SIGNATURE"
            ) from exc

        obj = event["data"]["object"]
        if event["type"] == "checkout.session.completed":
            metadata = obj.get("metadata") or {}
            pi = obj.get("payment_intent")
            currency = obj.get("currency")
            return VerifiedPaymentEvent(
                event_id=event["id"],
                provider="stripe",
                type="payment_succeeded",
                order_id=metadata.get("orderId") or obj.get("client_reference_id"),
                session_id=obj.get("id"),
                payment_intent_id=pi if isinstance(pi, str) else None,
                amount_paise=obj.get("amount_total"),
                currency=currency.upper() if isinstance(currency, str) else None,
            )

        if event["type"] == "checkout.session.expired":
            metadata = obj.get("metadata") or {}
            return VerifiedPaymentEvent(
                event_id=event["id"],
                provider="stripe",
                type="session_expired",
                order_id=metadata.get("orderId") or obj.get("client_reference_id"),
                session_id=obj.get("id"),
            )

        if event["type"] == "payment_intent.payment_failed":
            metadata = obj.get("metadata") or {}
            return VerifiedPaymentEvent(
                event_id=event["id"],
                provider="stripe",
                type="payment_failed",
                order_id=metadata.get("orderId"),
                payment_intent_id=obj.get("id"),
            )

        return VerifiedPaymentEvent(
            event_id=event["id"],
            provider="stripe",
            type="ignored",
        )

    def refund_payment(self, payment_intent_id: str, amount_paise: int) -> None:
        if not payment_intent_id:
            return
        self._client.refunds.create(
            params={"payment_intent": payment_intent_id, "amount": amount_paise}
        )


def create_payment_provider(settings: Settings) -> PaymentProvider:
    wants_stripe = settings.payment_provider == "stripe" or (
        settings.payment_provider == "auto" and bool(settings.stripe_secret_key)
    )
    if wants_stripe and settings.stripe_secret_key:
        return StripePaymentProvider(
            settings.stripe_secret_key, settings.stripe_webhook_secret
        )
    return MockPaymentProvider(settings.frontend_url, settings.mock_webhook_secret)
